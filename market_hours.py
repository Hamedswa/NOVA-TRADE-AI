"""
NOVA TRADE AI
market_hours.py

Gestion des horaires de marché — Moteur 2.

Marchés supportés :
    XAU/USD
    BTC/USD
    EUR/USD
    GBP/USD

Symboles internes :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD

Fonctions :
    - déterminer si un marché est ouvert ;
    - détecter une fermeture imminente ;
    - connaître le temps avant fermeture ;
    - connaître la prochaine ouverture ;
    - fournir un statut de marché.

IMPORTANT
---------
Ce module ne fait AUCUNE analyse de trading.

Il ne :
    - calcule pas de score ;
    - calcule pas de RR ;
    - définit pas Entry ;
    - définit pas SL ;
    - définit pas TP ;
    - valide pas un setup ;
    - rejette pas un setup.

Il fournit uniquement l'information horaire
utilisée par le reste du système.

Les horaires par défaut restent configurables
car les horaires exacts peuvent dépendre du broker
ou du fournisseur de marché.
"""

from __future__ import annotations

import os

from datetime import (
    datetime,
    time,
    timedelta,
    timezone,
)


# ============================================================
# MARCHÉS SUPPORTÉS
# ============================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)


DISPLAY_SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
}


# ============================================================
# NORMALISATION
# ============================================================

def normalize_symbol(
    symbol: str,
) -> str:
    """
    Normalise un symbole.

    Exemples :

        XAUUSD  -> XAUUSD
        XAU/USD -> XAUUSD
        BTC/USD -> BTCUSD
        EUR-USD -> EURUSD
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
    Retourne la représentation lisible du symbole.
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
# TYPE DE MARCHÉ
# ============================================================

CRYPTO_SYMBOLS = {
    "BTCUSD",
}

FOREX_SYMBOLS = {
    "EURUSD",
    "GBPUSD",
}

CFD_SYMBOLS = {
    "XAUUSD",
}


def is_crypto(
    symbol: str,
) -> bool:
    """
    BTC/USD est disponible 24/7.
    """

    return (
        normalize_symbol(symbol)
        in CRYPTO_SYMBOLS
    )


def is_forex(
    symbol: str,
) -> bool:
    """
    EUR/USD et GBP/USD sont des marchés Forex.
    """

    return (
        normalize_symbol(symbol)
        in FOREX_SYMBOLS
    )


def is_cfd(
    symbol: str,
) -> bool:
    """
    XAU/USD est traité ici comme CFD/marché
    avec pause quotidienne configurable.
    """

    return (
        normalize_symbol(symbol)
        in CFD_SYMBOLS
    )


# ============================================================
# HORAIRES FOREX / XAU
# ============================================================

# ------------------------------------------------------------
# OUVERTURE HEBDOMADAIRE
# ------------------------------------------------------------

FOREX_WEEKLY_OPEN = os.getenv(
    "FOREX_WEEKLY_OPEN",
    "22:00",
).strip()


# ------------------------------------------------------------
# FERMETURE HEBDOMADAIRE
# ------------------------------------------------------------

FOREX_WEEKLY_CLOSE = os.getenv(
    "FOREX_WEEKLY_CLOSE",
    "22:00",
).strip()


# ------------------------------------------------------------
# PAUSE QUOTIDIENNE XAU/USD
# ------------------------------------------------------------

XAU_PAUSE_START = os.getenv(
    "XAU_PAUSE_START",
    "21:00",
).strip()


XAU_PAUSE_END = os.getenv(
    "XAU_PAUSE_END",
    "22:00",
).strip()


# ------------------------------------------------------------
# BUFFER AVANT FERMETURE
# ------------------------------------------------------------

MARKET_CLOSE_BUFFER_MINUTES = int(
    os.getenv(
        "MARKET_CLOSE_BUFFER_MINUTES",
        "30",
    )
)


# ============================================================
# VALIDATION CONFIGURATION
# ============================================================

if MARKET_CLOSE_BUFFER_MINUTES < 0:
    raise ValueError(
        "MARKET_CLOSE_BUFFER_MINUTES "
        "ne peut pas être négatif."
    )


# ============================================================
# OUTILS INTERNES
# ============================================================

def _parse_time(
    value: str,
) -> time:
    """
    Convertit HH:MM en datetime.time.
    """

    try:

        hour, minute = map(
            int,
            value.split(":"),
        )

        if not (
            0 <= hour <= 23
        ):
            raise ValueError

        if not (
            0 <= minute <= 59
        ):
            raise ValueError

        return time(
            hour=hour,
            minute=minute,
        )

    except (
        ValueError,
        TypeError,
    ):

        raise ValueError(
            f"Heure invalide : {value!r}. "
            "Format attendu : HH:MM"
        )


def _now_utc() -> datetime:
    """
    Heure actuelle UTC.
    """

    return datetime.now(
        timezone.utc
    )


def _ensure_utc(
    value: datetime,
) -> datetime:
    """
    Garantit un datetime UTC aware.
    """

    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _combine_utc(
    date_value,
    time_value: time,
) -> datetime:
    """
    Combine une date et une heure en UTC.
    """

    return datetime.combine(
        date_value,
        time_value,
        tzinfo=timezone.utc,
    )


# ============================================================
# HORAIRES HEBDOMADAIRES
# ============================================================

def _is_weekly_closed(
    symbol: str,
    now: datetime,
) -> bool:
    """
    Vérifie la fermeture hebdomadaire.

    BTCUSD :
        jamais fermé.

    EURUSD / GBPUSD / XAUUSD :
        fermeture hebdomadaire selon la configuration.
    """

    normalized = normalize_symbol(
        symbol
    )

    if normalized == "BTCUSD":
        return False

    weekly_open = _parse_time(
        FOREX_WEEKLY_OPEN
    )

    weekly_close = _parse_time(
        FOREX_WEEKLY_CLOSE
    )

    weekday = now.weekday()
    current_time = now.time()

    # --------------------------------------------------------
    # SAMEDI
    # --------------------------------------------------------

    if weekday == 5:
        return True

    # --------------------------------------------------------
    # DIMANCHE
    # --------------------------------------------------------

    if weekday == 6:

        return (
            current_time
            < weekly_open
        )

    # --------------------------------------------------------
    # VENDREDI
    # --------------------------------------------------------

    if weekday == 4:

        return (
            current_time
            >= weekly_close
        )

    return False


# ============================================================
# PAUSE QUOTIDIENNE XAU/USD
# ============================================================

def _is_xau_daily_pause(
    symbol: str,
    now: datetime,
) -> bool:
    """
    Vérifie la pause quotidienne de XAU/USD.
    """

    normalized = normalize_symbol(
        symbol
    )

    if normalized != "XAUUSD":
        return False

    pause_start = _parse_time(
        XAU_PAUSE_START
    )

    pause_end = _parse_time(
        XAU_PAUSE_END
    )

    current_time = now.time()

    # --------------------------------------------------------
    # PAUSE DANS LA MÊME JOURNÉE
    # --------------------------------------------------------

    if pause_start < pause_end:

        return (
            pause_start
            <= current_time
            < pause_end
        )

    # --------------------------------------------------------
    # PAUSE TRAVERSANT MINUIT
    # --------------------------------------------------------

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
    Retourne True si le marché est considéré ouvert.

    BTCUSD :
        24/7.

    EURUSD / GBPUSD :
        horaires Forex.

    XAUUSD :
        horaires hebdomadaires + pause quotidienne.
    """

    normalized = normalize_symbol(
        symbol
    )

    # Symbole inconnu = pas de statut exploitable.
    if normalized not in SUPPORTED_SYMBOLS:
        return False

    if now is None:
        now = _now_utc()
    else:
        now = _ensure_utc(now)

    # --------------------------------------------------------
    # BTC/USD
    # --------------------------------------------------------

    if normalized == "BTCUSD":
        return True

    # --------------------------------------------------------
    # FERMETURE HEBDOMADAIRE
    # --------------------------------------------------------

    if _is_weekly_closed(
        normalized,
        now,
    ):
        return False

    # --------------------------------------------------------
    # PAUSE XAU/USD
    # --------------------------------------------------------

    if _is_xau_daily_pause(
        normalized,
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

    BTC/USD :
        None car disponible 24/7.

    EUR/USD / GBP/USD :
        fermeture hebdomadaire.

    XAU/USD :
        pause quotidienne ou fermeture hebdomadaire,
        selon laquelle arrive en premier.
    """

    normalized = normalize_symbol(
        symbol
    )

    if normalized == "BTCUSD":
        return None

    weekly_close = _parse_time(
        FOREX_WEEKLY_CLOSE
    )

    candidates: list[datetime] = []

    # --------------------------------------------------------
    # PAUSE XAU/USD
    # --------------------------------------------------------

    if normalized == "XAUUSD":

        pause_start = _parse_time(
            XAU_PAUSE_START
        )

        candidate = _combine_utc(
            now.date(),
            pause_start,
        )

        if candidate <= now:

            candidate += timedelta(
                days=1
            )

        candidates.append(
            candidate
        )

    # --------------------------------------------------------
    # FERMETURE HEBDOMADAIRE
    # --------------------------------------------------------

    days_until_friday = (
        4 - now.weekday()
    ) % 7

    friday = (
        now.date()
        + timedelta(
            days=days_until_friday
        )
    )

    weekly_candidate = _combine_utc(
        friday,
        weekly_close,
    )

    if weekly_candidate <= now:

        weekly_candidate += timedelta(
            days=7
        )

    candidates.append(
        weekly_candidate
    )

    if not candidates:
        return None

    return min(
        candidates
    )


# ============================================================
# MINUTES AVANT FERMETURE
# ============================================================

def minutes_until_market_close(
    symbol: str,
    now: datetime | None = None,
) -> int | None:
    """
    Retourne le nombre entier de minutes avant
    la prochaine fermeture.

    None signifie :
        - marché 24/7 ;
        - ou marché actuellement fermé.
    """

    normalized = normalize_symbol(
        symbol
    )

    if normalized not in SUPPORTED_SYMBOLS:
        return None

    if normalized == "BTCUSD":
        return None

    if now is None:
        now = _now_utc()
    else:
        now = _ensure_utc(now)

    if not is_market_open(
        normalized,
        now,
    ):
        return None

    close_dt = _next_market_close(
        normalized,
        now,
    )

    if close_dt is None:
        return None

    seconds = (
        close_dt - now
    ).total_seconds()

    if seconds <= 0:
        return 0

    return int(
        seconds // 60
    )


# ============================================================
# FERMETURE IMMINENTE
# ============================================================

def is_market_closing_soon(
    symbol: str,
    now: datetime | None = None,
) -> bool:
    """
    Indique si le marché ouvert approche
    d'une fermeture programmée.
    """

    minutes = (
        minutes_until_market_close(
            symbol,
            now,
        )
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
    Retourne la prochaine ouverture connue.

    Si le marché est actuellement ouvert,
    retourne maintenant.

    BTC/USD :
        retourne maintenant car 24/7.
    """

    normalized = normalize_symbol(
        symbol
    )

    if normalized not in SUPPORTED_SYMBOLS:
        return None

    if now is None:
        now = _now_utc()
    else:
        now = _ensure_utc(now)

    # --------------------------------------------------------
    # BTC/USD
    # --------------------------------------------------------

    if normalized == "BTCUSD":
        return now

    # --------------------------------------------------------
    # MARCHÉ DÉJÀ OUVERT
    # --------------------------------------------------------

    if is_market_open(
        normalized,
        now,
    ):
        return now

    # --------------------------------------------------------
    # PAUSE XAU/USD
    # --------------------------------------------------------

    if normalized == "XAUUSD":

        pause_end = _parse_time(
            XAU_PAUSE_END
        )

        candidate = _combine_utc(
            now.date(),
            pause_end,
        )

        if candidate > now:

            # On vérifie que l'ouverture
            # quotidienne n'est pas dépassée
            # par la fermeture hebdomadaire.
            if now.weekday() < 5:

                return candidate

    # --------------------------------------------------------
    # OUVERTURE HEBDOMADAIRE
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

        candidate += timedelta(
            days=7
        )

    return candidate


# ============================================================
# STATUT DU MARCHÉ
# ============================================================

def market_status(
    symbol: str,
    now: datetime | None = None,
) -> str:
    """
    Statuts possibles :

        OPEN
        CLOSING_SOON
        CLOSED
        UNSUPPORTED
    """

    normalized = normalize_symbol(
        symbol
    )

    if normalized not in SUPPORTED_SYMBOLS:
        return "UNSUPPORTED"

    if not is_market_open(
        normalized,
        now,
    ):
        return "CLOSED"

    if is_market_closing_soon(
        normalized,
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
    Retourne les informations horaires
    du marché demandé.
    """

    normalized = normalize_symbol(
        symbol
    )

    if now is None:
        now = _now_utc()
    else:
        now = _ensure_utc(now)

    status = market_status(
        normalized,
        now,
    )

    minutes = (
        minutes_until_market_close(
            normalized,
            now,
        )
    )

    next_open = next_market_open(
        normalized,
        now,
    )

    return {
        "symbol": normalized,
        "display_symbol": display_symbol(
            normalized
        ),
        "status": status,
        "is_open": (
            status
            in {
                "OPEN",
                "CLOSING_SOON",
            }
        ),
        "closing_soon": (
            status
            == "CLOSING_SOON"
        ),
        "minutes_until_close": minutes,
        "next_open": (
            next_open.isoformat()
            if next_open is not None
            else None
        ),
        "is_crypto": is_crypto(
            normalized
        ),
        "is_forex": is_forex(
            normalized
        ),
        "is_cfd": is_cfd(
            normalized
        ),
    }


# ============================================================
# INFORMATIONS TOUS LES MARCHÉS
# ============================================================

def get_all_market_hours_info(
    now: datetime | None = None,
) -> dict[str, dict]:
    """
    Retourne les horaires des quatre marchés.
    """

    if now is None:
        now = _now_utc()

    return {
        symbol: get_market_hours_info(
            symbol,
            now,
        )
        for symbol in SUPPORTED_SYMBOLS
    }


# ============================================================
# VALIDATION LOCALE
# ============================================================

def validate_configuration() -> None:
    """
    Vérifie la cohérence de la configuration.
    """

    _parse_time(
        FOREX_WEEKLY_OPEN
    )

    _parse_time(
        FOREX_WEEKLY_CLOSE
    )

    _parse_time(
        XAU_PAUSE_START
    )

    _parse_time(
        XAU_PAUSE_END
    )

    if MARKET_CLOSE_BUFFER_MINUTES < 0:

        raise ValueError(
            "Le buffer de fermeture "
            "ne peut pas être négatif."
        )


validate_configuration()


# ============================================================
# TEST DIRECT
# ============================================================

if __name__ == "__main__":

    print("=" * 64)
    print("NOVA TRADE AI — MARKET HOURS")
    print("=" * 64)

    for symbol in SUPPORTED_SYMBOLS:

        info = get_market_hours_info(
            symbol
        )

        print(
            f"{info['display_symbol']:8} | "
            f"{info['status']:14} | "
            f"ouvert={info['is_open']} | "
            f"fermeture={info['minutes_until_close']}"
        )

    print("=" * 64)