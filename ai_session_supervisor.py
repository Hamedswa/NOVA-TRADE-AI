"""
NOVA TRADE AI
AI Session Supervisor

Rôle EXCLUSIVEMENT INFORMATIONNEL.

Ce module :
- informe de l'ouverture des sessions ;
- informe de la fermeture des sessions ;
- surveille les sessions Tokyo, Londres et New York ;
- fournit l'état courant des sessions.

Ce module NE DOIT JAMAIS :
- générer un signal ;
- modifier un signal ;
- valider/rejeter un signal ;
- calculer un score ;
- modifier le RR ;
- intervenir dans le moteur de trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURATION
# ============================================================

UTC = ZoneInfo("UTC")

SESSIONS = {
    "TOKYO": {
        "timezone": "Asia/Tokyo",
        "open": 9,
        "close": 18,
    },
    "LONDON": {
        "timezone": "Europe/London",
        "open": 8,
        "close": 17,
    },
    "NEW_YORK": {
        "timezone": "America/New_York",
        "open": 8,
        "close": 17,
    },
}


# ============================================================
# DATA MODEL
# ============================================================

@dataclass(frozen=True)
class SessionStatus:
    name: str
    is_open: bool
    local_time: str
    timezone: str
    action: str | None = None


# ============================================================
# AI SESSION SUPERVISOR
# ============================================================

class AISessionSupervisor:
    """
    Superviseur informationnel des sessions de marché.

    IMPORTANT :
    Cette classe n'a aucun accès au moteur de signal.
    """

    def __init__(self):
        self._previous_states: dict[str, bool] = {}

        for session_name in SESSIONS:
            self._previous_states[session_name] = False

    # --------------------------------------------------------
    # UTILITAIRES
    # --------------------------------------------------------

    @staticmethod
    def _get_local_datetime(session_name: str, now_utc: datetime) -> datetime:
        """Convertit l'heure UTC vers le fuseau de la session."""

        timezone_name = SESSIONS[session_name]["timezone"]
        timezone = ZoneInfo(timezone_name)

        return now_utc.astimezone(timezone)

    # --------------------------------------------------------
    # ÉTAT D'UNE SESSION
    # --------------------------------------------------------

    def get_session_status(
        self,
        session_name: str,
        now_utc: datetime | None = None,
    ) -> SessionStatus:
        """Retourne l'état courant d'une session."""

        session_name = session_name.upper()

        if session_name not in SESSIONS:
            raise ValueError(
                f"Session inconnue : {session_name}. "
                f"Sessions disponibles : {list(SESSIONS)}"
            )

        if now_utc is None:
            now_utc = datetime.now(UTC)

        local_dt = self._get_local_datetime(session_name, now_utc)

        config = SESSIONS[session_name]

        hour = local_dt.hour

        is_open = config["open"] <= hour < config["close"]

        return SessionStatus(
            name=session_name,
            is_open=is_open,
            local_time=local_dt.strftime("%H:%M"),
            timezone=config["timezone"],
        )

    # --------------------------------------------------------
    # SURVEILLANCE DES SESSIONS
    # --------------------------------------------------------

    def check_sessions(
        self,
        now_utc: datetime | None = None,
    ) -> list[SessionStatus]:
        """
        Vérifie les sessions.

        Retourne uniquement les changements :
        - OPEN
        - CLOSE

        Les états sans changement ne génèrent aucune notification.
        """

        if now_utc is None:
            now_utc = datetime.now(UTC)

        events: list[SessionStatus] = []

        for session_name in SESSIONS:

            status = self.get_session_status(
                session_name,
                now_utc,
            )

            previous_state = self._previous_states[session_name]

            # Ouverture
            if status.is_open and not previous_state:

                event = SessionStatus(
                    name=status.name,
                    is_open=True,
                    local_time=status.local_time,
                    timezone=status.timezone,
                    action="OPEN",
                )

                events.append(event)

            # Fermeture
            elif not status.is_open and previous_state:

                event = SessionStatus(
                    name=status.name,
                    is_open=False,
                    local_time=status.local_time,
                    timezone=status.timezone,
                    action="CLOSE",
                )

                events.append(event)

            self._previous_states[session_name] = status.is_open

        return events

    # --------------------------------------------------------
    # MESSAGE D'INFORMATION
    # --------------------------------------------------------

    @staticmethod
    def format_session_message(
        status: SessionStatus,
    ) -> str:
        """Transforme un événement de session en message Telegram."""

        if status.action == "OPEN":

            return (
                f"🟢 SESSION {status.name} — OUVERTE\n\n"
                f"🕐 Heure locale : {status.local_time}\n"
                f"🌍 Fuseau : {status.timezone}\n\n"
                f"NOVA TRADE AI vous informe de l'ouverture "
                f"de cette session."
            )

        if status.action == "CLOSE":

            return (
                f"🔴 SESSION {status.name} — FERMÉE\n\n"
                f"🕐 Heure locale : {status.local_time}\n"
                f"🌍 Fuseau : {status.timezone}\n\n"
                f"NOVA TRADE AI vous informe de la fermeture "
                f"de cette session."
            )

        return ""


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    supervisor = AISessionSupervisor()

    print("NOVA TRADE AI — SESSION SUPERVISOR")
    print("=" * 45)

    statuses = supervisor.check_sessions()

    if not statuses:
        print("Aucun changement de session.")

    for status in statuses:
        print()
        print(AISessionSupervisor.format_session_message(status))