"""
NOVA TRADE AI
market_hours.py

Gestion des horaires de marché.

Objectifs :
- savoir si un marché est ouvert ;
- détecter une fermeture imminente ;
- empêcher les nouveaux signaux lorsque le marché est fermé ;
- fournir le nombre de minutes avant la fermeture ;
- garder les horaires configurables via les variables d'environnement.

IMPORTANT :
Les horaires exacts peuvent varier selon le broker.
Les valeurs par défaut sont donc configurables.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone


# ============================================================
# CONFIGURATION
# ============================================================

# Cryptos considérées comme disponibles 24/7.
CRYPTO_SYMBOLS = {
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "BNB/USD",
    "XRP/USD",
}


# ------------------------------------------------------------
# HORAIRES FOREX / CFD
# ------------------------------------------------------------

# Ouverture hebdomadaire par défaut : dimanche 22:00 UTC
FOREX_WEEKLY_OPEN = os.getenv(
    "FOREX_WEEKLY_OPEN",
    "22:00",
)

# Fermeture hebdomadaire par défaut : vendredi 22:00 UTC
FOREX_WEEKLY_CLOSE = os.getenv(
    "FOREX_WEEKLY_CLOSE",
    "22:00",
)


# ------------------------------------------------------------
# PAUSE QUOTIDIENNE XAU/USD
# ------------------------------------------------------------

# Valeurs par défaut :
# fermeture/pause : 21:00 UTC
# réouverture      : 22:00 UTC
#
# Ces valeurs peuvent être modifiées dans Railway.

XAU_PAUSE_START = os.getenv(
    "XAU_PAUSE_START",
    "21:00",
)

XAU_PAUSE_END = os.getenv(
    "XAU_PAUSE_END",
    "22:00",
)


# ------------------------------------------------------------
# BUFFER AVANT FERMETURE
# ------------------------------------------------------------

# Aucun nouveau signal dans les X dernières minutes
# avant une fermeture programmée.

MARKET_CLOSE_BUFFER_MINUTES = int(
    os.getenv(
        "MARKET_CLOSE_BUFFER_MINUTES",
        "30",
    )
)


# ============================================================
# OUTILS INTERNES
# ============================================================

def _parse_time(value: str) -> time:
    """
    Convertit 'HH:MM' en objet time.
    """

    try:
        hour, minute = map(int, value.split(":"))

        if not (0 <= hour <= 23):
            raise ValueError

        if not (0 <= minute <= 59):
            raise ValueError

        return time(
            hour=hour,
            minute=minute,
        )

    except (ValueError, TypeError):
        raise ValueError(
            f"Heure invalide : {value!r}. "
            f"Format attendu : HH:MM"
        )


def _now_utc() -> datetime:
    """
    Retourne l'heure actuelle en UTC.
    """

    return datetime.now(timezone.utc)


def _combine_utc(
    date_value,
    time_value: time,
) -> datetime:
    """
    Combine une date et une heure dans le fuseau UTC.
    """

    return datetime.combine(
        date_value,
        time_value,
        tzinfo=timezone.utc,
    )


# ============================================================
# IDENTIFICATION DU MARCHÉ
# ============================================================

def is_crypto(symbol: str) -> bool:
    """
    Retourne True si le symbole est une crypto.
    """

    return symbol.upper().strip() in CRYPTO_SYMBOLS


def is_forex_or_cfd(symbol: str) -> bool:
    """
    Retourne True pour les marchés Forex / CFD.
    """

    return not is_crypto(symbol)


# ============================================================
# HORAIRES HEBDOMADAIRES
# ============================================================

def _is_weekly_closed(
    symbol: str,
    now: datetime,
) -> bool:
    """
    Vérifie si le marché est fermé à cause du week-end.

    Crypto :
        jamais fermé pour cette logique.

    Forex / CFD :
        fermé du vendredi soir au dimanche soir.
    """

    if is_crypto(symbol):
        return False

    weekday = now.weekday()
    current_time = now.time()

    weekly_open = _parse_time(
        FOREX_WEEKLY_OPEN
    )

    weekly_close = _parse_time(
        FOREX_WEEKLY_CLOSE
    )

    # Samedi : fermé.
    if weekday == 5:
        return True

    # Dimanche :
    # avant l'heure d'ouverture -> fermé.
    if weekday == 6:
        return current_time < weekly_open

    # Vendredi :
    # après l'heure de fermeture -> fermé.
    if weekday == 4:
        return current_time >= weekly_close

    return False


# ============================================================
# PAUSE XAU/USD
# ============================================================

def _is_xau_daily_pause(
    symbol: str,
    now: datetime,
) -> bool:
    """
    Vérifie la pause quotidienne de XAU/USD.
    """

    if symbol.upper().strip() != "XAU/USD":
        return False

    pause_start = _parse_time(
        XAU_PAUSE_START
    )

    pause_end = _parse_time(
        XAU_PAUSE_END
    )

    current_time = now.time()

    # Pause normale dans la même journée.
    if pause_start < pause_end:
        return (
            pause_start
            <= current_time
            < pause_end
        )

    # Gestion d'une pause traversant minuit.
    return (
        current_time >= pause_start
        or current_time < pause_end
    )


# ============================================================
# MARCHÉ OUVERT ?
# ============================================================

def is_market_open(
    symbol: str,
    now: datetime | None = None,
) -> bool:
    """
    Détermine si le marché est actuellement ouvert.

    Crypto :
        24/7.

    Forex :
        dimanche soir -> vendredi soir.

    XAU/USD :
        Forex/CFD + pause quotidienne configurable.
    """

    symbol = symbol.upper().strip()

    if now is None:
        now = _now_utc()

    # On s'assure que la date utilisée est UTC.
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    # Crypto : 24/7.
    if is_crypto(symbol):
        return True

    # Fermeture hebdomadaire.
    if _is_weekly_closed(
        symbol,
        now,
    ):
        return False

    # Pause quotidienne XAU/USD.
    if _is_xau_daily_pause(
        symbol,
        now,
    ):
        return False

    return True


# ============================================================
# PROCHAINE FERMETURE
# ============================================================

def _next_market_close(
    symbol: str,
    now: datetime,
) -> datetime | None:
    """
    Retourne la prochaine fermeture connue.
    """

    symbol = symbol.upper().strip()

    if is_crypto(symbol):
        return None

    weekly_close = _parse_time(
        FOREX_WEEKLY_CLOSE
    )

    candidates: list[datetime] = []

    # --------------------------------------------------------
    # Fermeture quotidienne XAU
    # --------------------------------------------------------

    if symbol == "XAU/USD":

        pause_start = _parse_time(
            XAU_PAUSE_START
        )

        candidate = _combine_utc(
            now.date(),
            pause_start,
        )

        if candidate > now:
            candidates.append(candidate)

        else:
            candidates.append(
                candidate + timedelta(days=1)
            )

    # --------------------------------------------------------
    # Fermeture hebdomadaire
    # --------------------------------------------------------

    days_until_friday = (
        4 - now.weekday()
    ) % 7

    friday = (
        now.date()
        + timedelta(days=days_until_friday)
    )

    weekly_candidate = _combine_utc(
        friday,
        weekly_close,
    )

    if weekly_candidate <= now:
        weekly_candidate += timedelta(days=7)

    candidates.append(
        weekly_candidate
    )

    if not candidates:
        return None

    return min(candidates)


# ============================================================
# MINUTES AVANT FERMETURE
# ============================================================

def minutes_until_market_close(
    symbol: str,
    now: datetime | None = None,
) -> int | None:
    """
    Retourne le nombre de minutes avant la prochaine fermeture.

    Retourne None pour les cryptos.
    Retourne None si le marché est déjà fermé.
    """

    symbol = symbol.upper().strip()

    if is_crypto(symbol):
        return None

    if now is None:
        now = _now_utc()

    if now.tzinfo is None:
        now = now.replace(
            tzinfo=timezone.utc
        )
    else:
        now = now.astimezone(
            timezone.utc
        )

    if not is_market_open(
        symbol,
        now,
    ):
        return None

    close_dt = _next_market_close(
        symbol,
        now,
    )

    if close_dt is None:
        return None

    seconds = (
        close_dt - now
    ).total_seconds()

    return max(
        0,
        int(seconds // 60),
    )


# ============================================================
# FERMETURE IMMINENTE ?
# ============================================================

def is_market_closing_soon(
    symbol: str,
    now: datetime | None = None,
) -> bool:
    """
    Retourne True si le marché va fermer
    dans le délai MARKET_CLOSE_BUFFER_MINUTES.
    """

    minutes = minutes_until_market_close(
        symbol,
        now,
    )

    if minutes is None:
        return False

    return (
        minutes
        <= MARKET_CLOSE_BUFFER_MINUTES
    )


# ============================================================
# PROCHAINE OUVERTURE
# ============================================================

def next_market_open(
    symbol: str,
    now: datetime | None = None,
) -> datetime | None:
    """
    Retourne approximativement la prochaine ouverture.

    Les horaires restent configurables car le broker
    peut utiliser des horaires différents.
    """

    symbol = symbol.upper().strip()

    if is_crypto(symbol):
        return now or _now_utc()

    if now is None:
        now = _now_utc()

    if now.tzinfo is None:
        now = now.replace(
            tzinfo=timezone.utc
        )
    else:
        now = now.astimezone(
            timezone.utc
        )

    # Si le marché est déjà ouvert, aucune attente.
    if is_market_open(symbol, now):
        return now

    # --------------------------------------------------------
    # XAU/USD : fin de pause quotidienne
    # --------------------------------------------------------

    if symbol == "XAU/USD":

        pause_end = _parse_time(
            XAU_PAUSE_END
        )

        candidate = _combine_utc(
            now.date(),
            pause_end,
        )

        if candidate > now:
            return candidate

    # --------------------------------------------------------
    # Ouverture hebdomadaire
    # --------------------------------------------------------

    weekly_open = _parse_time(
        FOREX_WEEKLY_OPEN
    )

    days_until_sunday = (
        6 - now.weekday()
    ) % 7

    candidate = _combine_utc(
        now.date()
        + timedelta(
            days=days_until_sunday
        ),
        weekly_open,
    )

    if candidate <= now:
        candidate += timedelta(days=7)

    return candidate


# ============================================================
# STATUT DU MARCHÉ
# ============================================================

def market_status(
    symbol: str,
    now: datetime | None = None,
) -> str:
    """
    Retourne :

    OPEN
    CLOSING_SOON
    CLOSED
    """

    if not is_market_open(
        symbol,
        now,
    ):
        return "CLOSED"

    if is_market_closing_soon(
        symbol,
        now,
    ):
        return "CLOSING_SOON"

    return "OPEN"


# ============================================================
# INFORMATIONS COMPLÈTES
# ============================================================

def get_market_hours_info(
    symbol: str,
    now: datetime | None = None,
) -> dict:
    """
    Retourne toutes les informations utiles
    pour le pipeline, Telegram et le monitor.
    """

    if now is None:
        now = _now_utc()

    status = market_status(
        symbol,
        now,
    )

    minutes = minutes_until_market_close(
        symbol,
        now,
    )

    next_open = next_market_open(
        symbol,
        now,
    )

    return {
        "symbol": symbol.upper().strip(),
        "status": status,
        "is_open": status != "CLOSED",
        "closing_soon": status == "CLOSING_SOON",
        "minutes_until_close": minutes,
        "next_open": (
            next_open.isoformat()
            if next_open is not None
            else None
        ),
    }