"""
NOVA TRADE AI
Economic News Supervisor
--------------------------------
ROLE:
- Information uniquement
- Surveillance des annonces économiques HIGH
- Explication des annonces avec Groq
- Aucun impact sur le moteur de trading

IMPORTANT:
Ce module NE DOIT PAS :
- générer BUY / SELL
- calculer un score
- calculer un RR
- proposer Entry / SL / TP
- valider ou rejeter un signal
- bloquer ou débloquer une entrée
- modifier le moteur de trading
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import requests


# ============================================================
# CONFIGURATION
# ============================================================

SUPERVISOR_NEWS_ENABLED = (
    os.getenv("SUPERVISOR_NEWS_ENABLED", "true").lower()
    == "true"
)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()

FINNHUB_ECONOMIC_CALENDAR_URL = (
    "https://finnhub.io/api/v1/calendar/economic"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)

REQUEST_TIMEOUT = int(
    os.getenv("SUPERVISOR_NEWS_TIMEOUT", "8")
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
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    country: Optional[str] = None


# ============================================================
# HELPERS
# ============================================================

def _normalize_impact(value) -> str:
    if value is None:
        return "UNKNOWN"

    value = str(value).strip().upper()

    if value in ("HIGH", "3", "3.0"):
        return "HIGH"

    if value in ("MEDIUM", "MODERATE", "2", "2.0"):
        return "MEDIUM"

    if value in ("LOW", "1", "1.0"):
        return "LOW"

    return value


def _parse_datetime(value) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt

    value = str(value).strip()

    if not value:
        return None

    # ISO 8601
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except ValueError:
        pass

    # Formats courants
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


# ============================================================
# ECONOMIC NEWS SUPERVISOR
# ============================================================

class EconomicNewsSupervisor:

    def __init__(self):
        self.events: List[SupervisorEconomicEvent] = []
        self.last_update: Optional[datetime] = None

    # --------------------------------------------------------
    # FETCH FINNHUB
    # --------------------------------------------------------

    def fetch_events(self) -> List[SupervisorEconomicEvent]:

        if not SUPERVISOR_NEWS_ENABLED:
            print("[NEWS SUPERVISOR] Désactivé.")
            self.events = []
            return []

        if not FINNHUB_API_KEY:
            print(
                "[NEWS SUPERVISOR] FINNHUB_API_KEY "
                "manquante."
            )
            self.events = []
            return []

        now = datetime.now(timezone.utc)

        from_timestamp = int(now.timestamp())

        to_datetime = now + timedelta(
            hours=LOOKAHEAD_HOURS
        )

        to_timestamp = int(to_datetime.timestamp())

        params = {
            "from": now.strftime("%Y-%m-%d"),
            "to": to_datetime.strftime("%Y-%m-%d"),
            "token": FINNHUB_API_KEY,
        }

        try:

            response = requests.get(
                FINNHUB_ECONOMIC_CALENDAR_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            events = self._parse_response(data)

            # Garder uniquement les événements futurs
            # et HIGH.
            filtered = []

            for event in events:

                timestamp = int(
                    event.event_time.timestamp()
                )

                if (
                    event.impact == "HIGH"
                    and timestamp >= from_timestamp
                    and timestamp <= to_timestamp
                ):
                    filtered.append(event)

            filtered.sort(
                key=lambda event: event.event_time
            )

            self.events = filtered
            self.last_update = now

            print(
                f"[NEWS SUPERVISOR] "
                f"{len(filtered)} annonce(s) HIGH récupérée(s)."
            )

            return filtered

        except requests.RequestException as exc:

            print(
                "[NEWS SUPERVISOR] "
                f"Erreur Finnhub : {exc}"
            )

            self.events = []

            return []

        except Exception as exc:

            print(
                "[NEWS SUPERVISOR] "
                f"Erreur inattendue : {exc}"
            )

            self.events = []

            return []

    # --------------------------------------------------------
    # PARSE FINNHUB
    # --------------------------------------------------------

    def _parse_response(self, data) -> List[SupervisorEconomicEvent]:

        if not isinstance(data, dict):
            return []

        raw_events = data.get("economicCalendar", [])

        if not isinstance(raw_events, list):
            return []

        parsed = []

        for item in raw_events:

            if not isinstance(item, dict):
                continue

            impact = _normalize_impact(
                item.get("impact")
            )

            if impact != "HIGH":
                continue

            event_time = _parse_datetime(
                item.get("time")
            )

            if event_time is None:
                event_time = _parse_datetime(
                    item.get("datetime")
                )

            if event_time is None:
                continue

            title = (
                item.get("event")
                or item.get("title")
                or "Economic Event"
            )

            currency = (
                item.get("currency")
                or ""
            )

            country = (
                item.get("country")
                or ""
            )

            actual = item.get("actual")
            forecast = item.get("estimate")

            if forecast is None:
                forecast = item.get("forecast")

            previous = item.get("prev")

            if previous is None:
                previous = item.get("previous")

            parsed.append(
                SupervisorEconomicEvent(
                    title=str(title),
                    currency=str(currency),
                    impact=impact,
                    event_time=event_time,
                    actual=(
                        str(actual)
                        if actual is not None
                        else None
                    ),
                    forecast=(
                        str(forecast)
                        if forecast is not None
                        else None
                    ),
                    previous=(
                        str(previous)
                        if previous is not None
                        else None
                    ),
                    country=str(country),
                )
            )

        return parsed

    # --------------------------------------------------------
    # NEXT EVENT
    # --------------------------------------------------------

    def get_next_event(
        self,
    ) -> Optional[SupervisorEconomicEvent]:

        now = datetime.now(timezone.utc)

        future_events = [
            event
            for event in self.events
            if event.event_time >= now
        ]

        if not future_events:
            return None

        return min(
            future_events,
            key=lambda event: event.event_time
        )

    # --------------------------------------------------------
    # UPCOMING EVENTS
    # --------------------------------------------------------

    def get_upcoming_events(
        self,
        limit: int = 5,
    ) -> List[SupervisorEconomicEvent]:

        now = datetime.now(timezone.utc)

        future_events = [
            event
            for event in self.events
            if event.event_time >= now
        ]

        future_events.sort(
            key=lambda event: event.event_time
        )

        return future_events[:limit]

    # --------------------------------------------------------
    # AI PROMPT
    # --------------------------------------------------------

    def build_ai_prompt(
        self,
        event: SupervisorEconomicEvent,
    ) -> str:

        return f"""
Tu es le superviseur informatif des annonces économiques
de NOVA TRADE AI.

Ton rôle est UNIQUEMENT pédagogique et informatif.

Annonce économique :
- Nom : {event.title}
- Devise : {event.currency}
- Pays : {event.country}
- Impact : {event.impact}
- Heure : {event.event_time.isoformat()}
- Actual : {event.actual}
- Prévision : {event.forecast}
- Précédent : {event.previous}

Explique cette annonce en français simple.

Donne :

1. Ce que mesure cette annonce.
2. Pourquoi elle est importante.
3. Ce que signifie généralement une valeur supérieure
   ou inférieure aux attentes.
4. Les principaux actifs ou devises potentiellement
   concernés de manière générale.
5. Pourquoi le marché peut devenir plus volatil autour
   de cette publication.

INTERDICTIONS ABSOLUES :

Tu ne dois jamais :
- donner BUY ou SELL ;
- faire une analyse technique ;
- calculer un score ;
- calculer un RR ;
- proposer Entry ;
- proposer Stop Loss ;
- proposer Take Profit ;
- donner un signal ;
- valider ou rejeter un signal ;
- bloquer ou débloquer une entrée ;
- modifier une décision du moteur de trading ;
- donner une recommandation de trading.

Tu es uniquement un interprète pédagogique
de l'annonce économique.

Réponds clairement et brièvement.
"""

    # --------------------------------------------------------
    # GROQ EXPLANATION
    # --------------------------------------------------------

    def explain_event(
        self,
        event: SupervisorEconomicEvent,
    ) -> str:

        if not GROQ_API_KEY:
            return (
                "Explication IA indisponible : "
                "GROQ_API_KEY manquante."
            )

        prompt = self.build_ai_prompt(event)

        url = (
            "https://api.groq.com/openai/v1/"
            "chat/completions"
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
                        "strictement informatif."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.2,
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            choices = data.get("choices", [])

            if not choices:
                return (
                    "Aucune explication IA disponible."
                )

            message = choices[0].get(
                "message",
                {}
            )

            content = message.get(
                "content",
                ""
            )

            if not content:
                return (
                    "Aucune explication IA disponible."
                )

            return content.strip()

        except requests.RequestException as exc:

            print(
                "[NEWS SUPERVISOR] "
                f"Erreur Groq : {exc}"
            )

            return (
                "Explication IA temporairement "
                "indisponible."
            )

        except Exception as exc:

            print(
                "[NEWS SUPERVISOR] "
                f"Erreur IA inattendue : {exc}"
            )

            return (
                "Explication IA temporairement "
                "indisponible."
            )

    # --------------------------------------------------------
    # TELEGRAM MESSAGE
    # --------------------------------------------------------

    def format_event_message(
        self,
        event: SupervisorEconomicEvent,
        explanation: str,
    ) -> str:

        event_time = event.event_time.astimezone(
            timezone.utc
        ).strftime("%d/%m/%Y %H:%M UTC")

        return (
            "📰 <b>ALERTE ÉCONOMIQUE</b>\n\n"
            f"📌 <b>{event.title}</b>\n"
            f"💱 Devise : {event.currency}\n"
            f"🌍 Pays : {event.country or 'N/A'}\n"
            f"🔴 Impact : <b>{event.impact}</b>\n"
            f"🕒 Heure : {event_time}\n\n"
            "📊 <b>Données</b>\n"
            f"• Actual : {event.actual or 'N/A'}\n"
            f"• Prévision : {event.forecast or 'N/A'}\n"
            f"• Précédent : {event.previous or 'N/A'}\n\n"
            "🤖 <b>Explication</b>\n"
            f"{explanation}\n\n"
            "ℹ️ <i>Information économique uniquement. "
            "Aucun signal de trading.</i>"
        )


# ============================================================
# INSTANCE GLOBALE
# ============================================================

economic_news_supervisor = EconomicNewsSupervisor()


# ============================================================
# HELPERS PUBLICS
# ============================================================

def update_supervisor_news():

    return economic_news_supervisor.fetch_events()


def get_next_supervisor_event():

    return economic_news_supervisor.get_next_event()


# ============================================================
# TEST LOCAL TEMPORAIRE
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("NOVA TRADE AI")
    print("TEST ECONOMIC NEWS SUPERVISOR")
    print("=" * 60)

    print("\n[1] Vérification de la configuration")

    print(
        "SUPERVISOR_NEWS_ENABLED :",
        SUPERVISOR_NEWS_ENABLED,
    )

    print(
        "FINNHUB_API_KEY :",
        "OK" if FINNHUB_API_KEY else "MANQUANTE",
    )

    print(
        "GROQ_API_KEY :",
        "OK" if GROQ_API_KEY else "MANQUANTE",
    )

    print(
        "GROQ_MODEL :",
        GROQ_MODEL,
    )

    print("\n[2] Récupération des annonces HIGH...")

    events = economic_news_supervisor.fetch_events()

    print(
        f"\nNombre d'annonces HIGH : {len(events)}"
    )

    if not events:

        print(
            "\n❌ Aucune annonce HIGH récupérée."
        )

        print(
            "Vérifie FINNHUB_API_KEY et la réponse "
            "de Finnhub."
        )

    else:

        print(
            "\n[3] Annonces trouvées"
        )

        for index, event in enumerate(
            events[:5],
            start=1,
        ):

            print("\n" + "-" * 60)

            print(
                f"Annonce #{index}"
            )

            print(
                "Titre      :",
                event.title,
            )

            print(
                "Devise     :",
                event.currency,
            )

            print(
                "Impact     :",
                event.impact,
            )

            print(
                "Pays       :",
                event.country,
            )

            print(
                "Date/heure :",
                event.event_time,
            )

            print(
                "Actual     :",
                event.actual,
            )

            print(
                "Forecast   :",
                event.forecast,
            )

            print(
                "Previous   :",
                event.previous,
            )

        # ----------------------------------------------------
        # TEST GROQ SUR LA PREMIÈRE ANNONCE
        # ----------------------------------------------------

        first_event = events[0]

        print(
            "\n[4] Test de l'explication IA..."
        )

        explanation = (
            economic_news_supervisor
            .explain_event(first_event)
        )

        print("\n" + "-" * 60)
        print("EXPLICATION GROQ")
        print("-" * 60)

        print(explanation)

        # ----------------------------------------------------
        # TEST FORMAT TELEGRAM
        # ----------------------------------------------------

        print(
            "\n[5] Test du message Telegram..."
        )

        telegram_message = (
            economic_news_supervisor
            .format_event_message(
                first_event,
                explanation,
            )
        )

        print("\n" + "-" * 60)
        print("MESSAGE TELEGRAM")
        print("-" * 60)

        print(telegram_message)

    print("\n" + "=" * 60)
    print("TEST TERMINÉ")
    print("=" * 60)