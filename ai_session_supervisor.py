"""
NOVA TRADE AI
ai_session_supervisor.py

AI SESSION SUPERVISOR

RÔLE EXCLUSIVEMENT INFORMATIONNEL.

Ce module :
    - informe de l'ouverture des sessions ;
    - informe de la fermeture des sessions ;
    - surveille Tokyo, Londres et New York ;
    - fournit l'état courant des sessions ;
    - fonctionne indépendamment du moteur de trading.

IMPORTANT
---------
Ce module ne possède AUCUNE autorité sur le Moteur 2.

Il ne doit JAMAIS :
    - générer un signal ;
    - générer BUY / SELL ;
    - valider un setup ;
    - rejeter un setup ;
    - produire READY_FOR_SIGNAL ;
    - calculer un score ;
    - calculer un RR ;
    - modifier un RR ;
    - définir Entry ;
    - définir SL ;
    - définir TP ;
    - bloquer un signal ;
    - modifier un signal ;
    - annuler un signal ;
    - intervenir dans moteur2_validation.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURATION
# ============================================================

UTC = ZoneInfo("UTC")


SESSIONS = {
    "TOKYO": {
        "timezone": "Asia/Tokyo",
        "open": "09:00",
        "close": "18:00",
    },
    "LONDON": {
        "timezone": "Europe/London",
        "open": "08:00",
        "close": "17:00",
    },
    "NEW_YORK": {
        "timezone": "America/New_York",
        "open": "08:00",
        "close": "17:00",
    },
}


# ============================================================
# MODÈLE
# ============================================================

@dataclass(frozen=True)
class SessionStatus:
    """
    État informationnel d'une session.
    """

    name: str
    is_open: bool
    local_time: str
    timezone: str
    action: Optional[str] = None


# ============================================================
# SUPERVISEUR
# ============================================================

class AISessionSupervisor:
    """
    Superviseur informationnel des sessions.

    Cette classe ne communique avec aucun moteur
    de signal et ne possède aucune logique de trading.
    """

    def __init__(self) -> None:

        self._previous_states: Dict[
            str,
            bool,
        ] = {
            session_name: False
            for session_name in SESSIONS
        }

    # ========================================================
    # UTILITAIRES
    # ========================================================

    @staticmethod
    def _normalize_session_name(
        session_name: str,
    ) -> str:
        """
        Normalise et valide le nom d'une session.
        """

        normalized = (
            str(session_name)
            .strip()
            .upper()
        )

        if normalized not in SESSIONS:

            raise ValueError(
                f"Session inconnue : {normalized}. "
                f"Sessions disponibles : "
                f"{', '.join(SESSIONS.keys())}"
            )

        return normalized

    @staticmethod
    def _parse_time(
        value: str,
    ) -> tuple[int, int]:
        """
        Convertit HH:MM en heures et minutes.
        """

        hour_text, minute_text = (
            value.split(":")
        )

        hour = int(hour_text)
        minute = int(minute_text)

        if not 0 <= hour <= 23:
            raise ValueError(
                f"Heure invalide : {value}"
            )

        if not 0 <= minute <= 59:
            raise ValueError(
                f"Minute invalide : {value}"
            )

        return hour, minute

    @classmethod
    def _is_inside_schedule(
        cls,
        local_dt: datetime,
        session_name: str,
    ) -> bool:
        """
        Vérifie si l'heure locale se trouve
        dans les horaires de la session.

        La fonction gère également les horaires
        qui traverseraient minuit.
        """

        config = SESSIONS[
            session_name
        ]

        open_hour, open_minute = (
            cls._parse_time(
                config["open"]
            )
        )

        close_hour, close_minute = (
            cls._parse_time(
                config["close"]
            )
        )

        current_minutes = (
            local_dt.hour * 60
            + local_dt.minute
        )

        open_minutes = (
            open_hour * 60
            + open_minute
        )

        close_minutes = (
            close_hour * 60
            + close_minute
        )

        # Session normale.
        if open_minutes < close_minutes:

            return (
                open_minutes
                <= current_minutes
                < close_minutes
            )

        # Session traversant minuit.
        if open_minutes > close_minutes:

            return (
                current_minutes >= open_minutes
                or current_minutes < close_minutes
            )

        # Même heure d'ouverture et de fermeture :
        # configuration considérée comme fermée.
        return False

    @staticmethod
    def _ensure_utc(
        now_utc: datetime,
    ) -> datetime:
        """
        Garantit que la date fournie est interprétée
        comme une date UTC.

        Si elle est naïve, elle est considérée comme UTC.
        """

        if now_utc.tzinfo is None:

            return now_utc.replace(
                tzinfo=UTC
            )

        return now_utc.astimezone(
            UTC
        )

    # ========================================================
    # HEURE LOCALE
    # ========================================================

    @classmethod
    def _get_local_datetime(
        cls,
        session_name: str,
        now_utc: datetime,
    ) -> datetime:
        """
        Convertit une date UTC vers le fuseau
        de la session.
        """

        session_name = (
            cls._normalize_session_name(
                session_name
            )
        )

        now_utc = cls._ensure_utc(
            now_utc
        )

        timezone_name = (
            SESSIONS[
                session_name
            ]["timezone"]
        )

        timezone = ZoneInfo(
            timezone_name
        )

        return now_utc.astimezone(
            timezone
        )

    # ========================================================
    # ÉTAT D'UNE SESSION
    # ========================================================

    def get_session_status(
        self,
        session_name: str,
        now_utc: Optional[
            datetime
        ] = None,
    ) -> SessionStatus:
        """
        Retourne l'état courant d'une session.
        """

        session_name = (
            self._normalize_session_name(
                session_name
            )
        )

        if now_utc is None:

            now_utc = datetime.now(
                UTC
            )

        local_dt = (
            self._get_local_datetime(
                session_name,
                now_utc,
            )
        )

        config = SESSIONS[
            session_name
        ]

        is_open = (
            self._is_inside_schedule(
                local_dt,
                session_name,
            )
        )

        return SessionStatus(
            name=session_name,
            is_open=is_open,
            local_time=local_dt.strftime(
                "%H:%M"
            ),
            timezone=config[
                "timezone"
            ],
        )

    # ========================================================
    # ÉTAT DE TOUTES LES SESSIONS
    # ========================================================

    def get_all_sessions_status(
        self,
        now_utc: Optional[
            datetime
        ] = None,
    ) -> List[SessionStatus]:
        """
        Retourne l'état actuel des trois sessions.
        """

        if now_utc is None:

            now_utc = datetime.now(
                UTC
            )

        return [
            self.get_session_status(
                session_name,
                now_utc,
            )
            for session_name in SESSIONS
        ]

    # ========================================================
    # SURVEILLANCE
    # ========================================================

    def check_sessions(
        self,
        now_utc: Optional[
            datetime
        ] = None,
    ) -> List[SessionStatus]:
        """
        Vérifie les changements d'état.

        Retourne uniquement :
            OPEN
            CLOSE

        Les états sans changement ne génèrent
        aucune notification.

        IMPORTANT :
            ces événements sont uniquement informatifs.
        """

        if now_utc is None:

            now_utc = datetime.now(
                UTC
            )

        now_utc = self._ensure_utc(
            now_utc
        )

        events: List[
            SessionStatus
        ] = []

        for session_name in SESSIONS:

            status = (
                self.get_session_status(
                    session_name,
                    now_utc,
                )
            )

            previous_state = (
                self._previous_states[
                    session_name
                ]
            )

            # ------------------------------------------------
            # Ouverture
            # ------------------------------------------------

            if (
                status.is_open
                and not previous_state
            ):

                events.append(
                    SessionStatus(
                        name=status.name,
                        is_open=True,
                        local_time=status.local_time,
                        timezone=status.timezone,
                        action="OPEN",
                    )
                )

            # ------------------------------------------------
            # Fermeture
            # ------------------------------------------------

            elif (
                not status.is_open
                and previous_state
            ):

                events.append(
                    SessionStatus(
                        name=status.name,
                        is_open=False,
                        local_time=status.local_time,
                        timezone=status.timezone,
                        action="CLOSE",
                    )
                )

            self._previous_states[
                session_name
            ] = status.is_open

        return events

    # ========================================================
    # RESET DE L'ÉTAT
    # ========================================================

    def reset_states(self) -> None:
        """
        Réinitialise les états internes.

        Utilitaire uniquement pour le redémarrage
        ou les tests.
        """

        for session_name in SESSIONS:

            self._previous_states[
                session_name
            ] = False

    # ========================================================
    # MESSAGE TELEGRAM
    # ========================================================

    @staticmethod
    def format_session_message(
        status: SessionStatus,
    ) -> str:
        """
        Transforme un événement de session
        en message Telegram.

        Aucun conseil de trading n'est généré.
        """

        if status.action == "OPEN":

            return (
                f"🟢 <b>SESSION "
                f"{status.name} — OUVERTE</b>\n\n"
                f"🕐 Heure locale : "
                f"<b>{status.local_time}</b>\n"
                f"🌍 Fuseau : "
                f"<b>{status.timezone}</b>\n\n"
                "ℹ️ NOVA TRADE AI vous informe "
                "simplement de l'ouverture de "
                "cette session."
            )

        if status.action == "CLOSE":

            return (
                f"🔴 <b>SESSION "
                f"{status.name} — FERMÉE</b>\n\n"
                f"🕐 Heure locale : "
                f"<b>{status.local_time}</b>\n"
                f"🌍 Fuseau : "
                f"<b>{status.timezone}</b>\n\n"
                "ℹ️ NOVA TRADE AI vous informe "
                "simplement de la fermeture de "
                "cette session."
            )

        return ""

    # ========================================================
    # STATUT DU SUPERVISEUR
    # ========================================================

    @staticmethod
    def get_supervisor_status() -> Dict[str, object]:
        """
        Retourne les capacités du superviseur.

        Toutes les capacités de décision de trading
        sont explicitement désactivées.
        """

        return {
            "enabled": True,
            "informational_only": True,
            "sessions": list(
                SESSIONS.keys()
            ),
            "can_generate_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_block_signal": False,
            "can_modify_signal": False,
            "can_modify_score": False,
            "can_modify_rr": False,
            "can_modify_entry": False,
            "can_modify_sl": False,
            "can_modify_tp": False,
            "final_validation_owner": (
                "moteur2_validation.py"
            ),
        }


# ============================================================
# INSTANCE UTILITAIRE
# ============================================================

session_supervisor = (
    AISessionSupervisor()
)


# ============================================================
# TEST LOCAL
# ============================================================

def test_ai_session_supervisor() -> Dict[str, object]:
    """
    Test autonome du superviseur.

    Ne touche jamais au Moteur 2.
    """

    try:

        now_utc = datetime.now(
            UTC
        )

        statuses = (
            session_supervisor
            .get_all_sessions_status(
                now_utc
            )
        )

        return {
            "success": True,
            "sessions": len(
                statuses
            ),
            "open_sessions": sum(
                1
                for status in statuses
                if status.is_open
            ),
            "informational_only": True,
            "can_generate_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_block_signal": False,
        }

    except Exception as exc:

        return {
            "success": False,
            "sessions": 0,
            "open_sessions": 0,
            "informational_only": True,
            "can_generate_signal": False,
            "can_validate_signal": False,
            "can_reject_signal": False,
            "can_block_signal": False,
            "error": str(exc),
        }


# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":

    import logging

    logging.basicConfig(
        level=logging.INFO
    )

    supervisor = (
        AISessionSupervisor()
    )

    print()
    print(
        "=============================================="
    )
    print(
        " NOVA TRADE AI - AI SESSION SUPERVISOR"
    )
    print(
        "=============================================="
    )

    print()

    for status in (
        supervisor
        .get_all_sessions_status()
    ):

        state = (
            "OUVERTE"
            if status.is_open
            else "FERMÉE"
        )

        print(
            f"{status.name:<10} "
            f"{state:<8} "
            f"{status.local_time} "
            f"({status.timezone})"
        )

    print()

    result = (
        test_ai_session_supervisor()
    )

    print(
        f"Test : {result['success']}"
    )

    print(
        f"Sessions : {result['sessions']}"
    )

    print(
        f"Sessions ouvertes : "
        f"{result['open_sessions']}"
    )

    print(
        f"Mode informatif : "
        f"{result['informational_only']}"
    )

    print(
        "=============================================="
    )