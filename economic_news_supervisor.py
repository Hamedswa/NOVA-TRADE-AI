"""
NOVA TRADE AI
economic_news_supervisor.py
MODULE INFORMATIONNEL UNIQUEMENT.
Rôle :
- récupérer les annonces économiques importantes ;
- détecter les annonces HIGH ;
- conserver Actual / Forecast / Previous ;
- préparer une explication claire de l'annonce ;
- utiliser Groq UNIQUEMENT comme interpréteur ;
- fournir un texte destiné à Telegram.
IMPORTANT :
Ce module NE DOIT JAMAIS :
- générer BUY ou SELL ;
- calculer ou modifier un score ;
- calculer ou modifier un RR ;
- définir Entry / SL / TP ;
- valider ou rejeter un signal ;
- bloquer une entrée ;
- modifier le moteur de trading.
Ce module est totalement indépendant de :
- analyse.py
- score.py
- rr.py
- structure.py
- gestion_signal.py
- surveillance.py
- economic_calendar.py
Architecture :
Finnhub
   ↓
economic_news_supervisor.py
   ↓
Groq (interprétation uniquement)
   ↓
AI Session Supervisor
   ↓
Telegram
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import logging
import os
import requests
logger = logging.getLogger(__name__)
# ============================================================
# CONFIGURATION
# ============================================================
SUPERVISOR_NEWS_ENABLED = os.getenv(
    "SUPERVISOR_NEWS_ENABLED",
    "true",
).lower() in ("true", "1", "yes", "on")
FINNHUB_API_KEY = os.getenv(
    "FINNHUB_API_KEY",
    "",
).strip()
FINNHUB_ECONOMIC_CALENDAR_URL = (
    "https://finnhub.io/api/v1/calendar/economic"
)
GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    "",
).strip()
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile",
).strip()
REQUEST_TIMEOUT = int(
    os.getenv(
        "SUPERVISOR_NEWS_TIMEOUT",
        "8",
    )
)
LOOKAHEAD_HOURS = int(
    os.getenv(
        "SUPERVISOR_NEWS_LOOKAHEAD_HOURS",
        "48",
    )
)
# ============================================================
# MODÈLE
# ============================================================
@dataclass
class SupervisorEconomicEvent:
    """
    Événement économique destiné exclusivement
    au AI Session Supervisor.
    """
    title: str
    currency: str
    impact: str
    event_time: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    country: Optional[str] = None
    @property
    def is_high_impact(self) -> bool:
        return self.impact.upper() == "HIGH"
# ============================================================
# OUTILS INTERNES
# ============================================================
def _normalize_impact(value: Any) -> str:
    """
    Normalise le niveau d'impact.
    """
    if value is None:
        return "LOW"
    text = str(value).strip().upper()
    mapping = {
        "3": "HIGH",
        "2": "MEDIUM",
        "1": "LOW",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW",
        "HIGH IMPACT": "HIGH",
        "MEDIUM IMPACT": "MEDIUM",
        "LOW IMPACT": "LOW",
    }
    return mapping.get(text, "LOW")
def _parse_datetime(
    value: Any,
) -> Optional[datetime]:
    """
    Convertit différentes représentations
    de date en datetime UTC.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        # Timestamp Unix
        if text.isdigit():
            try:
                timestamp = int(text)
                if timestamp > 10_000_000_000:
                    timestamp /= 1000
                dt = datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                )
            except (ValueError, OverflowError):
                return None
        else:
            try:
                dt = datetime.fromisoformat(
                    text.replace(
                        "Z",
                        "+00:00",
                    )
                )
            except ValueError:
                formats = (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%Y-%m-%d",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M",
                )
                dt = None
                for fmt in formats:
                    try:
                        dt = datetime.strptime(
                            text,
                            fmt,
                        )
                        break
                    except ValueError:
                        continue
                if dt is None:
                    return None
    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )
    return dt.astimezone(
        timezone.utc
    )
# ============================================================
# SUPERVISOR ECONOMIC NEWS
# ============================================================
class EconomicNewsSupervisor:
    """
    Gestionnaire des annonces économiques
    pour le AI Session Supervisor.
    Aucune fonction de trading.
    """
    def __init__(self) -> None:
        self.events: list[
            SupervisorEconomicEvent
        ] = []
        self.last_update: Optional[
            datetime
        ] = None
    # ========================================================
    # RÉCUPÉRATION DES ANNONCES
    # ========================================================
    def fetch_events(
        self,
    ) -> list[SupervisorEconomicEvent]:
        """
        Récupère les annonces HIGH depuis Finnhub.
        Aucun traitement de trading n'est effectué.
        """
        if not SUPERVISOR_NEWS_ENABLED:
            logger.info(
                "Economic News Supervisor désactivé."
            )
            return self.events
        if not FINNHUB_API_KEY:
            logger.warning(
                "FINNHUB_API_KEY absente."
            )
            return self.events
        now = datetime.now(
            timezone.utc
        )
        end = now + timedelta(
            hours=LOOKAHEAD_HOURS
        )
        params = {
            "from": now.strftime(
                "%Y-%m-%d"
            ),
            "to": end.strftime(
                "%Y-%m-%d"
            ),
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
            events = self._parse_response(
                data
            )
            self.events = events
            self.last_update = datetime.now(
                timezone.utc
            )
            logger.info(
                "Supervisor Economic News : "
                "%d annonce(s) HIGH.",
                len(events),
            )
            return events
        except requests.RequestException as exc:
            logger.warning(
                "Erreur Finnhub Supervisor : %s",
                exc,
            )
            return self.events
        except Exception as exc:
            logger.warning(
                "Erreur Economic News Supervisor : %s",
                exc,
            )
            return self.events
    # ========================================================
    # PARSING
    # ========================================================
    def _parse_response(
        self,
        data: Any,
    ) -> list[SupervisorEconomicEvent]:
        """
        Convertit la réponse Finnhub.
        """
        if not isinstance(
            data,
            dict,
        ):
            return []
        raw_events = data.get(
            "economicCalendar",
            [],
        )
        if not isinstance(
            raw_events,
            list,
        ):
            return []
        parsed = []
        for item in raw_events:
            if not isinstance(
                item,
                dict,
            ):
                continue
            impact = _normalize_impact(
                item.get("impact")
            )
            # Supervisor : HIGH uniquement
            if impact != "HIGH":
                continue
            title = (
                item.get("event")
                or item.get("name")
                or "Economic Event"
            )
            currency = str(
                item.get("currency")
                or ""
            ).strip().upper()
            event_time = _parse_datetime(
                item.get("time")
                or item.get("datetime")
                or item.get("date")
            )
            if event_time is None:
                continue
            actual = item.get("actual")
            forecast = item.get(
                "estimate"
            )
            if forecast is None:
                forecast = item.get(
                    "forecast"
                )
            previous = item.get(
                "prev"
            )
            if previous is None:
                previous = item.get(
                    "previous"
                )
            country = item.get(
                "country"
            )
            parsed.append(
                SupervisorEconomicEvent(
                    title=str(title),
                    currency=currency,
                    impact="HIGH",
                    event_time=event_time,
                    actual=(
                        None
                        if actual is None
                        else str(actual)
                    ),
                    forecast=(
                        None
                        if forecast is None
                        else str(forecast)
                    ),
                    previous=(
                        None
                        if previous is None
                        else str(previous)
                    ),
                    country=(
                        None
                        if country is None
                        else str(country)
                    ),
                )
            )
        parsed.sort(
            key=lambda event:
            event.event_time
        )
        return parsed
    # ========================================================
    # PROCHAINE ANNONCE
    # ========================================================
    def get_next_event(
        self,
        currency: Optional[str] = None,
    ) -> Optional[SupervisorEconomicEvent]:
        """
        Retourne la prochaine annonce HIGH.
        """
        now = datetime.now(
            timezone.utc
        )
        candidates = [
            event
            for event in self.events
            if event.event_time >= now
        ]
        if currency:
            currency = currency.upper()
            candidates = [
                event
                for event in candidates
                if event.currency == currency
            ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda event:
            event.event_time,
        )
    # ========================================================
    # ÉVÉNEMENTS IMMINENTS
    # ========================================================
    def get_upcoming_events(
        self,
        minutes: int = 60,
    ) -> list[SupervisorEconomicEvent]:
        """
        Retourne les annonces HIGH
        prévues dans les prochaines minutes.
        """
        now = datetime.now(
            timezone.utc
        )
        limit = now + timedelta(
            minutes=minutes
        )
        return [
            event
            for event in self.events
            if now
            <= event.event_time
            <= limit
        ]
    # ========================================================
    # PROMPT GROQ
    # ========================================================
    @staticmethod
    def build_ai_prompt(
        event: SupervisorEconomicEvent,
    ) -> str:
        """
        Construit le prompt d'interprétation.
        L'IA est explicitement limitée
        à l'information économique.
        """
        return f"""
Tu es l'interprète économique de NOVA TRADE AI.
Tu dois UNIQUEMENT expliquer une annonce économique.
Tu n'as AUCUN rôle dans le trading.
INTERDICTIONS ABSOLUES :
- ne pas donner BUY ;
- ne pas donner SELL ;
- ne pas proposer d'entrée ;
- ne pas proposer SL ;
- ne pas proposer TP ;
- ne pas donner de signal ;
- ne pas modifier un signal ;
- ne pas donner de score ;
- ne pas donner de RR ;
- ne pas dire de prendre ou fermer une position.
Annonce :
Nom : {event.title}
Devise : {event.currency}
Pays : {event.country or "N/A"}
Impact : {event.impact}
Heure UTC : {event.event_time.isoformat()}
Actual : {event.actual or "Non disponible"}
Forecast : {event.forecast or "Non disponible"}
Previous : {event.previous or "Non disponible"}
Explique simplement :
1. Ce qu'est cette annonce.
2. Pourquoi elle est importante.
3. Ce que signifie la comparaison
   Actual / Forecast / Previous lorsqu'elle existe.
4. Les principaux impacts économiques potentiels.
5. Quels marchés ou actifs peuvent généralement
   connaître davantage de volatilité.
Reste neutre et factuel.
Ne fais aucune recommandation de trading.
"""
    # ========================================================
    # INTERPRÉTATION GROQ
    # ========================================================
    def explain_event(
        self,
        event: SupervisorEconomicEvent,
    ) -> Optional[str]:
        """
        Demande à Groq d'expliquer l'annonce.
        Groq est utilisé uniquement comme interprète.
        """
        if not GROQ_API_KEY:
            logger.warning(
                "GROQ_API_KEY absente. "
                "Interprétation IA indisponible."
            )
            return None
        prompt = self.build_ai_prompt(
            event
        )
        url = (
            "https://api.groq.com/openai/v1/chat/completions"
        )
        headers = {
            "Authorization": (
                f"Bearer {GROQ_API_KEY}"
            ),
            "Content-Type": "application/json",
        }
        payload = {
            "model": GROQ_MODEL,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu es un interprète "
                        "économique neutre."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
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
            choices = data.get(
                "choices",
                [],
            )
            if not choices:
                return None
            message = choices[0].get(
                "message",
                {}
            )
            content = message.get(
                "content"
            )
            if not content:
                return None
            return str(content).strip()
        except requests.RequestException as exc:
            logger.warning(
                "Erreur Groq Economic Supervisor : %s",
                exc,
            )
            return None
        except Exception as exc:
            logger.warning(
                "Erreur interprétation économique : %s",
                exc,
            )
            return None
    # ========================================================
    # MESSAGE TELEGRAM
    # ========================================================
    def format_event_message(
        self,
        event: SupervisorEconomicEvent,
        explanation: Optional[str] = None,
    ) -> str:
        """
        Prépare une notification Telegram.
        """
        message = (
            "🚨 <b>ANNONCE ÉCONOMIQUE HIGH</b>\n\n"
            f"📰 <b>{event.title}</b>\n"
            f"💱 Devise : {event.currency}\n"
            f"🌍 Pays : {event.country or 'N/A'}\n"
            f"🔴 Impact : HIGH\n"
            f"🕐 Heure UTC : "
            f"{event.event_time.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"📊 Actual : "
            f"{event.actual or 'N/A'}\n"
            f"📈 Forecast : "
            f"{event.forecast or 'N/A'}\n"
            f"📉 Previous : "
            f"{event.previous or 'N/A'}\n"
        )
        if explanation:
            message += (
                "\n🧠 <b>INTERPRÉTATION</b>\n\n"
                f"{explanation}\n"
            )
        message += (
            "\nℹ️ Cette notification est "
            "strictement informative."
        )
        return message
# ============================================================
# INSTANCE GLOBALE
# ============================================================
economic_news_supervisor = (
    EconomicNewsSupervisor()
)
# ============================================================
# FONCTIONS SIMPLES
# ============================================================
def update_supervisor_news() -> list[
    SupervisorEconomicEvent
]:
    """
    Met à jour les annonces économiques
    du AI Session Supervisor.
    """
    return economic_news_supervisor.fetch_events()
def get_next_supervisor_event(
    currency: Optional[str] = None,
) -> Optional[SupervisorEconomicEvent]:
    """
    Retourne la prochaine annonce HIGH.
    """
    return economic_news_supervisor.get_next_event(
        currency
    )