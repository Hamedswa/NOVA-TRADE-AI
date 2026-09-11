"""
NOVA TRADE AI
economic_calendar.py

Calendrier économique informatif — Moteur 2.

Marchés supportés :
    XAU/USD
    BTC/USD
    EUR/USD
    GBP/USD

Rôle :
    - récupérer les annonces économiques ;
    - conserver uniquement les annonces HIGH ;
    - identifier les devises pertinentes ;
    - détecter les annonces HIGH proches ;
    - fournir des informations au supervisor / Telegram.

IMPORTANT
---------
Ce module est STRICTEMENT INFORMATIF.

Il ne doit JAMAIS :
    - valider un signal ;
    - rejeter un signal ;
    - bloquer un signal ;
    - modifier Entry ;
    - modifier SL ;
    - modifier TP ;
    - modifier le RR ;
    - modifier le score ;
    - influencer moteur2_validation.py.

Le moteur de validation reste exclusivement :
    moteur2_validation.py

En cas d'indisponibilité de Finnhub :
    NOVA TRADE AI continue normalement.
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
).lower() in {
    "true",
    "1",
    "yes",
    "on",
}


FINNHUB_API_KEY = os.getenv(
    "FINNHUB_API_KEY",
    "",
).strip()


FINNHUB_ECONOMIC_CALENDAR_URL = (
    "https://finnhub.io/api/v1/calendar/economic"
)


# ------------------------------------------------------------
# FENÊTRES INFORMATIVES
# ------------------------------------------------------------

HIGH_IMPACT_BEFORE_MINUTES = int(
    os.getenv(
        "HIGH_IMPACT_BEFORE_MINUTES",
        "30",
    )
)


HIGH_IMPACT_AFTER_MINUTES = int(
    os.getenv(
        "HIGH_IMPACT_AFTER_MINUTES",
        "15",
    )
)


ECONOMIC_CALENDAR_LOOKAHEAD_HOURS = int(
    os.getenv(
        "ECONOMIC_CALENDAR_LOOKAHEAD_HOURS",
        "48",
    )
)


REQUEST_TIMEOUT = int(
    os.getenv(
        "ECONOMIC_CALENDAR_TIMEOUT",
        "8",
    )
)


# ============================================================
# MARCHÉS SUPPORTÉS
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


# ============================================================
# MODÈLE
# ============================================================

@dataclass
class EconomicEvent:
    """
    Représente une annonce économique.
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
        Indique si l'événement est HIGH.
        """

        return (
            self.impact.upper()
            == "HIGH"
        )


# ============================================================
# NORMALISATION
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
    Retourne le symbole dans son format lisible.
    """

    normalized = normalize_symbol(
        symbol
    )

    return DISPLAY_SYMBOLS.get(
        normalized,
        normalized,
    )


def is_supported_symbol(
    symbol: str,
) -> bool:
    """
    Vérifie si le symbole appartient au Moteur 2.
    """

    return (
        normalize_symbol(symbol)
        in SUPPORTED_SYMBOLS
    )


# ============================================================
# DEVISES PERTINENTES
# ============================================================

def get_symbol_currencies(
    symbol: str,
) -> list[str]:
    """
    Retourne les devises pertinentes pour un actif.

    XAU/USD -> USD
    BTC/USD -> USD
    EUR/USD -> EUR + USD
    GBP/USD -> GBP + USD
    """

    normalized = normalize_symbol(
        symbol
    )

    mapping = {
        "XAUUSD": ["USD"],
        "BTCUSD": ["USD"],
        "EURUSD": ["EUR", "USD"],
        "GBPUSD": ["GBP", "USD"],
    }

    return mapping.get(
        normalized,
        [],
    )


# ============================================================
# OUTILS INTERNES
# ============================================================

def _normalize_impact(
    value: Any,
) -> str:
    """
    Normalise le niveau d'impact.
    """

    if value is None:
        return "LOW"

    text = (
        str(value)
        .strip()
        .upper()
    )

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

    return mapping.get(
        text,
        "LOW",
    )


def _parse_datetime(
    value: Any,
) -> Optional[datetime]:
    """
    Convertit une date quelconque en UTC.
    """

    if not value:
        return None

    if isinstance(
        value,
        datetime,
    ):

        dt = value

    else:

        text = str(
            value
        ).strip()

        # ----------------------------------------------------
        # Timestamp Unix
        # ----------------------------------------------------

        if text.isdigit():

            try:

                timestamp = int(
                    text
                )

                if timestamp > 10_000_000_000:
                    timestamp /= 1000

                dt = datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                )

            except (
                ValueError,
                OverflowError,
            ):

                return None

        else:

            dt = None

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
# CALENDRIER ÉCONOMIQUE
# ============================================================

class EconomicCalendar:
    """
    Gestionnaire informatif du calendrier économique.

    Les événements sont utilisés uniquement pour
    informer le supervisor / Telegram.

    Aucune décision de trading n'est produite.
    """

    def __init__(self) -> None:

        self.events: list[
            EconomicEvent
        ] = []

        self.last_update: Optional[
            datetime
        ] = None

        self.last_error: Optional[
            str
        ] = None

    # ========================================================
    # RÉCUPÉRATION
    # ========================================================

    def fetch_events(
        self,
    ) -> list[EconomicEvent]:
        """
        Récupère les annonces HIGH.

        En cas d'erreur :
            - conserve les dernières données ;
            - ne fait pas planter NOVA.
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

        end = (
            now
            + timedelta(
                hours=ECONOMIC_CALENDAR_LOOKAHEAD_HOURS
            )
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

            events = (
                self._parse_finnhub_response(
                    data
                )
            )

            events = [
                event
                for event in events
                if event.is_high_impact
            ]

            self.events = events

            self.last_update = (
                datetime.now(
                    timezone.utc
                )
            )

            self.last_error = None

            logger.info(
                "Finnhub : %d événement(s) "
                "HIGH récupéré(s).",
                len(events),
            )

            return events

        except requests.RequestException as exc:

            self.last_error = str(
                exc
            )

            logger.warning(
                "Erreur Finnhub : %s",
                exc,
            )

            return self.events

        except Exception as exc:

            self.last_error = str(
                exc
            )

            logger.warning(
                "Erreur calendrier économique : %s",
                exc,
            )

            return self.events

    # ========================================================
    # PARSING
    # ========================================================

    def _parse_finnhub_response(
        self,
        data: Any,
    ) -> list[EconomicEvent]:
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
            # IMPACT
            # ------------------------------------------------

            impact = _normalize_impact(
                item.get(
                    "impact"
                )
            )

            if impact != "HIGH":
                continue

            # ------------------------------------------------
            # TITRE
            # ------------------------------------------------

            title = (
                item.get("event")
                or item.get("name")
                or "Economic Event"
            )

            # ------------------------------------------------
            # DEVISE
            # ------------------------------------------------

            currency = (
                item.get("currency")
                or ""
            )

            currency = (
                str(currency)
                .strip()
                .upper()
            )

            if not currency:
                continue

            # ------------------------------------------------
            # DATE / HEURE
            # ------------------------------------------------

            raw_time = (
                item.get("time")
                or item.get("datetime")
                or item.get("date")
            )

            event_time = (
                _parse_datetime(
                    raw_time
                )
            )

            if event_time is None:
                continue

            # ------------------------------------------------
            # VALEURS
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
    # ÉVÉNEMENTS PERTINENTS
    # ========================================================

    def get_relevant_events(
        self,
        symbol: str,
        hours_ahead: int = 24,
    ) -> list[EconomicEvent]:
        """
        Retourne les annonces HIGH pertinentes.

        Cette fonction est informative uniquement.
        """

        currencies = (
            get_symbol_currencies(
                symbol
            )
        )

        if not currencies:
            return []

        now = datetime.now(
            timezone.utc
        )

        limit = (
            now
            + timedelta(
                hours=hours_ahead
            )
        )

        return [
            event
            for event in self.events
            if event.is_high_impact
            and event.currency
            in currencies
            and now
            <= event.event_time
            <= limit
        ]

    # ========================================================
    # ÉVÉNEMENT HIGH PROCHAIN
    # ========================================================

    def get_next_high_impact_event(
        self,
        symbol: str,
    ) -> Optional[EconomicEvent]:
        """
        Retourne la prochaine annonce HIGH
        pertinente.

        Aucun effet sur le moteur de trading.
        """

        currencies = (
            get_symbol_currencies(
                symbol
            )
        )

        if not currencies:
            return None

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
    # ÉVÉNEMENT HIGH PROCHE
    # ========================================================

    def get_high_impact_window(
        self,
        symbol: str,
        before_minutes: Optional[int] = None,
        after_minutes: Optional[int] = None,
    ) -> list[EconomicEvent]:
        """
        Retourne les événements HIGH situés
        dans la fenêtre temporelle demandée.

        Cette fonction ne bloque rien.
        Elle fournit uniquement une information.
        """

        before = (
            HIGH_IMPACT_BEFORE_MINUTES
            if before_minutes is None
            else max(
                0,
                int(before_minutes),
            )
        )

        after = (
            HIGH_IMPACT_AFTER_MINUTES
            if after_minutes is None
            else max(
                0,
                int(after_minutes),
            )
        )

        currencies = (
            get_symbol_currencies(
                symbol
            )
        )

        if not currencies:
            return []

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

        return [
            event
            for event in self.events
            if event.is_high_impact
            and event.currency
            in currencies
            and window_start
            <= event.event_time
            <= window_end
        ]

    # ========================================================
    # INFORMATION : HIGH IMMINENTE
    # ========================================================

    def has_high_impact_event(
        self,
        symbol: str,
        before_minutes: Optional[int] = None,
        after_minutes: Optional[int] = None,
    ) -> bool:
        """
        Indique uniquement si une annonce HIGH
        pertinente est proche.

        ATTENTION :
        True ne signifie PAS que le marché doit être bloqué.
        """

        return bool(
            self.get_high_impact_window(
                symbol,
                before_minutes,
                after_minutes,
            )
        )

    # ========================================================
    # STATUT INFORMATIF
    # ========================================================

    def get_status(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """
        Retourne l'état informatif du calendrier.

        Le champ 'blocking' est volontairement
        toujours False.

        Le champ 'can_affect_signal' est volontairement
        toujours False.

        Ces champs permettent d'éviter qu'un ancien
        composant interprète par erreur une annonce
        comme une autorisation de blocage.
        """

        normalized = normalize_symbol(
            symbol
        )

        relevant = (
            self.get_relevant_events(
                normalized,
                hours_ahead=24,
            )
        )

        nearby = (
            self.get_high_impact_window(
                normalized
            )
        )

        next_event = (
            self.get_next_high_impact_event(
                normalized
            )
        )

        return {
            "enabled": (
                ECONOMIC_CALENDAR_ENABLED
            ),
            "provider": "Finnhub",
            "symbol": normalized,
            "display_symbol": display_symbol(
                normalized
            ),
            "supported": is_supported_symbol(
                normalized
            ),

            "high_only": True,

            # ------------------------------------------------
            # INFORMATION UNIQUEMENT
            # ------------------------------------------------

            "informational_only": True,
            "blocking": False,
            "blocked": False,
            "can_affect_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_modify_signal": False,

            # ------------------------------------------------
            # DONNÉES
            # ------------------------------------------------

            "relevant_events": relevant,
            "nearby_high_events": nearby,
            "next_high_impact": next_event,

            "last_update": (
                self.last_update
            ),

            "last_error": (
                self.last_error
            ),
        }


# ============================================================
# INSTANCE GLOBALE
# ============================================================

economic_calendar = (
    EconomicCalendar()
)


# ============================================================
# FONCTIONS PUBLIQUES
# ============================================================

def update_economic_calendar() -> list[
    EconomicEvent
]:
    """
    Met à jour le calendrier économique.
    """

    return (
        economic_calendar.fetch_events()
    )


def get_economic_status(
    symbol: str,
) -> dict[str, Any]:
    """
    Interface simple pour Telegram,
    le supervisor ou le dashboard.

    Cette interface est informative uniquement.
    """

    return (
        economic_calendar.get_status(
            symbol
        )
    )


def get_relevant_economic_events(
    symbol: str,
    hours_ahead: int = 24,
) -> list[EconomicEvent]:
    """
    Retourne les annonces HIGH pertinentes.
    """

    return (
        economic_calendar.get_relevant_events(
            symbol,
            hours_ahead,
        )
    )


def get_next_economic_event(
    symbol: str,
) -> Optional[EconomicEvent]:
    """
    Retourne la prochaine annonce HIGH pertinente.
    """

    return (
        economic_calendar.get_next_high_impact_event(
            symbol
        )
    )


# ============================================================
# COMPATIBILITÉ SÉCURISÉE
# ============================================================

def economic_filter(
    symbol: str,
) -> tuple[bool, Optional[str]]:
    """
    Interface de compatibilité avec d'anciens appels.

    IMPORTANT :
    cette fonction NE BLOQUE PLUS rien.

    Elle retourne toujours :
        (False, raison_informative_ou_None)

    afin qu'un ancien appel ne puisse pas transformer
    le calendrier économique en filtre de trading.
    """

    status = (
        economic_calendar.get_status(
            symbol
        )
    )

    nearby = status.get(
        "nearby_high_events",
        [],
    )

    if nearby:

        event = nearby[0]

        reason = (
            "INFORMATION uniquement : "
            f"annonce HIGH {event.title} "
            f"({event.currency})"
        )

        return False, reason

    return False, None


# ============================================================
# ANCIENNE API — DÉSACTIVÉE
# ============================================================

def should_block_entry(
    symbol: str,
) -> tuple[bool, Optional[str]]:
    """
    Compatibilité avec l'ancienne API.

    Le calendrier économique n'a plus le droit
    de bloquer une entrée.

    Retourne donc TOUJOURS False.
    """

    return economic_filter(
        symbol
    )


# ============================================================
# TEST DIRECT
# ============================================================

if __name__ == "__main__":

    print("=" * 64)
    print(
        "NOVA TRADE AI — ECONOMIC CALENDAR"
    )
    print("=" * 64)

    print(
        "Mode : INFORMATION UNIQUEMENT"
    )

    for symbol in (
        "XAUUSD",
        "BTCUSD",
        "EURUSD",
        "GBPUSD",
    ):

        status = (
            economic_calendar.get_status(
                symbol
            )
        )

        print()
        print(
            f"{display_symbol(symbol)}"
        )

        print(
            f"  Supported       : "
            f"{status['supported']}"
        )

        print(
            f"  HIGH only       : "
            f"{status['high_only']}"
        )

        print(
            f"  Blocking        : "
            f"{status['blocking']}"
        )

        print(
            f"  Relevant events : "
            f"{len(status['relevant_events'])}"
        )

        print(
            f"  Nearby HIGH     : "
            f"{len(status['nearby_high_events'])}"
        )

    print()
    print("=" * 64)