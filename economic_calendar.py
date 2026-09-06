"""
NOVA TRADE AI
economic_calendar.py
Gestion des annonces économiques via Finnhub.
Objectifs :
- récupérer les événements économiques ;
- filtrer automatiquement les annonces HIGH uniquement ;
- identifier les devises pertinentes pour l'actif ;
- détecter les annonces HIGH imminentes ;
- protéger les nouvelles entrées avant/après les annonces majeures ;
- NE JAMAIS faire planter NOVA TRADE AI si Finnhub est indisponible.
IMPORTANT :
Ce module est un FILTRE DE RISQUE.
Il ne remplace jamais l'analyse technique
D1/H4 -> H1/M15 -> M5.
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
ECONOMIC_CALENDAR_ENABLED = os.getenv(
    "ECONOMIC_CALENDAR_ENABLED",
    "true",
).lower() in ("true", "1", "yes", "on")
# Clé API Finnhub.
#
# IMPORTANT :
# Ne jamais mettre la clé directement dans ce fichier.
# Elle doit être configurée dans Railway :
#
# FINNHUB_API_KEY=xxxxxxxx
#
FINNHUB_API_KEY = os.getenv(
    "FINNHUB_API_KEY",
    "",
).strip()
# Endpoint officiel Finnhub pour le calendrier économique.
FINNHUB_ECONOMIC_CALENDAR_URL = (
    "https://finnhub.io/api/v1/calendar/economic"
)
# Temps de protection AVANT une annonce HIGH.
HIGH_IMPACT_BEFORE_MINUTES = int(
    os.getenv(
        "HIGH_IMPACT_BEFORE_MINUTES",
        "30",
    )
)
# Temps de protection APRÈS une annonce HIGH.
HIGH_IMPACT_AFTER_MINUTES = int(
    os.getenv(
        "HIGH_IMPACT_AFTER_MINUTES",
        "15",
    )
)
# Nombre d'heures à récupérer dans le calendrier.
ECONOMIC_CALENDAR_LOOKAHEAD_HOURS = int(
    os.getenv(
        "ECONOMIC_CALENDAR_LOOKAHEAD_HOURS",
        "48",
    )
)
# Timeout HTTP.
REQUEST_TIMEOUT = int(
    os.getenv(
        "ECONOMIC_CALENDAR_TIMEOUT",
        "8",
    )
)
# ============================================================
# MODÈLE
# ============================================================
@dataclass
class EconomicEvent:
    """
    Représente une annonce économique HIGH.
    """
    title: str
    currency: str
    impact: str
    event_time: datetime
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    @property
    def is_high_impact(self) -> bool:
        """
        Vérifie si l'annonce est HIGH.
        """
        return self.impact.upper() == "HIGH"
# ============================================================
# OUTILS
# ============================================================
def _normalize_impact(value: Any) -> str:
    """
    Normalise le niveau d'impact fourni par Finnhub
    ou un éventuel fournisseur compatible.
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
        "HIGH IMP": "HIGH",
        "MEDIUM IMP": "MEDIUM",
        "LOW IMP": "LOW",
    }
    return mapping.get(text, "LOW")
def _parse_datetime(value: Any) -> Optional[datetime]:
    """
    Convertit différentes représentations de date
    en datetime UTC.
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
                # Protection contre les timestamps
                # exprimés en millisecondes.
                if timestamp > 10_000_000_000:
                    timestamp = timestamp / 1000
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
    # Si aucune timezone n'est fournie,
    # on considère UTC.
    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )
    return dt.astimezone(
        timezone.utc
    )
def normalize_symbol(symbol: str) -> str:
    """
    Convertit les symboles Forex/Crypto
    vers une forme standard.
    Exemples :
        XAU/USD -> XAUUSD
        EUR/USD -> EURUSD
        BTC/USD -> BTCUSD
    """
    return (
        str(symbol)
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
def get_symbol_currencies(
    symbol: str,
) -> list[str]:
    """
    Détermine les devises pertinentes pour un actif.
    XAU/USD -> USD
    BTC/USD -> USD
    EUR/USD -> EUR + USD
    GBP/USD -> GBP + USD
    """
    normalized = normalize_symbol(
        symbol
    )
    if normalized in (
        "XAUUSD",
        "BTCUSD",
        "ETHUSD",
        "SOLUSD",
    ):
        return ["USD"]
    if len(normalized) >= 6:
        return [
            normalized[:3],
            normalized[3:6],
        ]
    return []
# ============================================================
# CALENDRIER ÉCONOMIQUE
# ============================================================
class EconomicCalendar:
    """
    Gestionnaire du calendrier économique Finnhub.
    Le calendrier reste indépendant du moteur d'analyse.
    Si Finnhub est indisponible :
        -> NOVA TRADE AI continue de fonctionner.
        -> Les derniers événements connus sont conservés.
    """
    def __init__(self) -> None:
        self.events: list[EconomicEvent] = []
        self.last_update: Optional[
            datetime
        ] = None
    # --------------------------------------------------------
    # RÉCUPÉRATION FINNHUB
    # --------------------------------------------------------
    def fetch_events(self) -> list[EconomicEvent]:
        """
        Récupère les événements économiques HIGH
        depuis Finnhub.
        Les événements LOW/MEDIUM sont ignorés
        immédiatement afin de garder NOVA TRADE AI léger.
        """
        if not ECONOMIC_CALENDAR_ENABLED:
            logger.info(
                "Calendrier économique désactivé."
            )
            return self.events
        if not FINNHUB_API_KEY:
            logger.warning(
                "FINNHUB_API_KEY non configurée. "
                "Calendrier économique inactif."
            )
            return self.events
        now = datetime.now(
            timezone.utc
        )
        end = now + timedelta(
            hours=ECONOMIC_CALENDAR_LOOKAHEAD_HOURS
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
            events = self._parse_finnhub_response(
                data
            )
            # On ne conserve que HIGH.
            events = [
                event
                for event in events
                if event.is_high_impact
            ]
            self.events = events
            self.last_update = datetime.now(
                timezone.utc
            )
            logger.info(
                "Finnhub : %d événement(s) HIGH récupéré(s).",
                len(events),
            )
            return events
        except requests.RequestException as exc:
            logger.warning(
                "Erreur Finnhub : %s",
                exc,
            )
            return self.events
        except Exception as exc:
            logger.warning(
                "Erreur calendrier économique : %s",
                exc,
            )
            return self.events
    # --------------------------------------------------------
    # PARSING FINNHUB
    # --------------------------------------------------------
    def _parse_finnhub_response(
        self,
        data: Any,
    ) -> list[EconomicEvent]:
        """
        Convertit la réponse Finnhub
        en objets EconomicEvent.
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
        parsed: list[
            EconomicEvent
        ] = []
        for item in raw_events:
            if not isinstance(
                item,
                dict,
            ):
                continue
            # ------------------------------------------------
            # Impact
            # ------------------------------------------------
            impact = _normalize_impact(
                item.get(
                    "impact"
                )
            )
            # IMPORTANT :
            # NOVA TRADE AI ignore immédiatement
            # les annonces non HIGH.
            if impact != "HIGH":
                continue
            # ------------------------------------------------
            # Nom de l'événement
            # ------------------------------------------------
            title = (
                item.get("event")
                or item.get("name")
                or "Economic Event"
            )
            # ------------------------------------------------
            # Devise
            # ------------------------------------------------
            currency = (
                item.get("currency")
                or ""
            )
            currency = str(
                currency
            ).strip().upper()
            # ------------------------------------------------
            # Date / heure
            # ------------------------------------------------
            event_time = (
                item.get("time")
                or item.get("datetime")
                or item.get("date")
            )
            event_time = _parse_datetime(
                event_time
            )
            if event_time is None:
                continue
            # ------------------------------------------------
            # Valeurs économiques
            # ------------------------------------------------
            actual = item.get(
                "actual"
            )
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
            parsed.append(
                EconomicEvent(
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
                )
            )
        parsed.sort(
            key=lambda event:
            event.event_time
        )
        return parsed
    # ========================================================
    # RECHERCHE
    # ========================================================
    def get_relevant_events(
        self,
        symbol: str,
        hours_ahead: int = 24,
    ) -> list[EconomicEvent]:
        """
        Retourne uniquement les annonces HIGH
        concernant l'actif.
        """
        currencies = get_symbol_currencies(
            symbol
        )
        now = datetime.now(
            timezone.utc
        )
        limit = now + timedelta(
            hours=hours_ahead
        )
        relevant: list[
            EconomicEvent
        ] = []
        for event in self.events:
            if not event.is_high_impact:
                continue
            if event.currency not in currencies:
                continue
            if event.event_time < now:
                continue
            if event.event_time > limit:
                continue
            relevant.append(event)
        return relevant
    # ========================================================
    # ANNONCE HIGH IMMINENTE
    # ========================================================
    def has_high_impact_event(
        self,
        symbol: str,
        before_minutes: Optional[int] = None,
        after_minutes: Optional[int] = None,
    ) -> bool:
        """
        Vérifie si une annonce HIGH pertinente
        se trouve dans la fenêtre de protection.
        """
        before = (
            HIGH_IMPACT_BEFORE_MINUTES
            if before_minutes is None
            else before_minutes
        )
        after = (
            HIGH_IMPACT_AFTER_MINUTES
            if after_minutes is None
            else after_minutes
        )
        currencies = get_symbol_currencies(
            symbol
        )
        now = datetime.now(
            timezone.utc
        )
        window_start = (
            now
            - timedelta(
                minutes=after
            )
        )
        window_end = (
            now
            + timedelta(
                minutes=before
            )
        )
        for event in self.events:
            if not event.is_high_impact:
                continue
            if event.currency not in currencies:
                continue
            if (
                window_start
                <= event.event_time
                <= window_end
            ):
                return True
        return False
    # ========================================================
    # PROCHAINE ANNONCE HIGH
    # ========================================================
    def get_next_high_impact_event(
        self,
        symbol: str,
    ) -> Optional[EconomicEvent]:
        """
        Retourne la prochaine annonce HIGH
        pertinente pour l'actif.
        """
        currencies = get_symbol_currencies(
            symbol
        )
        now = datetime.now(
            timezone.utc
        )
        candidates = [
            event
            for event in self.events
            if event.is_high_impact
            and event.currency
            in currencies
            and event.event_time >= now
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda event:
            event.event_time,
        )
    # ========================================================
    # DÉCISION DE TRADING
    # ========================================================
    def should_block_entry(
        self,
        symbol: str,
    ) -> tuple[
        bool,
        Optional[str],
    ]:
        """
        Détermine si une nouvelle entrée
        doit être bloquée.
        Retour :
            (True, raison)
            (False, None)
        """
        if not ECONOMIC_CALENDAR_ENABLED:
            return False, None
        if self.has_high_impact_event(
            symbol
        ):
            event = (
                self.get_next_high_impact_event(
                    symbol
                )
            )
            if event:
                reason = (
                    "Annonce économique HIGH : "
                    f"{event.title} "
                    f"({event.currency})"
                )
            else:
                reason = (
                    "Annonce économique HIGH "
                    "dans la fenêtre de protection."
                )
            return True, reason
        return False, None
    # ========================================================
    # STATUT
    # ========================================================
    def get_status(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Retourne un état exploitable
        par le moteur principal.
        """
        relevant = (
            self.get_relevant_events(
                symbol,
                hours_ahead=24,
            )
        )
        blocked, reason = (
            self.should_block_entry(
                symbol
            )
        )
        next_event = (
            self.get_next_high_impact_event(
                symbol
            )
        )
        return {
            "enabled": (
                ECONOMIC_CALENDAR_ENABLED
            ),
            "provider": "Finnhub",
            "high_only": True,
            "symbol": symbol,
            "blocked": blocked,
            "reason": reason,
            "relevant_events": relevant,
            "next_high_impact": next_event,
            "last_update": self.last_update,
        }
# ============================================================
# INSTANCE GLOBALE
# ============================================================
economic_calendar = EconomicCalendar()
# ============================================================
# FONCTIONS SIMPLES
# ============================================================
def update_economic_calendar() -> list[
    EconomicEvent
]:
    """
    Met à jour le calendrier économique.
    """
    return economic_calendar.fetch_events()
def economic_filter(
    symbol: str,
) -> tuple[
    bool,
    Optional[str],
]:
    """
    Interface simple pour le moteur de stratégie.
    Exemple :
        blocked, reason = economic_filter("XAU/USD")
        if blocked:
            # ne pas entrer
    """
    return economic_calendar.should_block_entry(
        symbol
    )