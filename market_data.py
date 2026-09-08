"""
NOVA TRADE AI
market_data.py

MOTEUR CENTRAL DES DONNÉES DE MARCHÉ.

Objectifs :
    - Twelve Data
    - Cache intelligent
    - Protection anti-429
    - Réduction massive des requêtes inutiles
    - Réutilisation contrôlée des dernières données valides
    - Retry avec backoff
    - Aucun affichage de clé API
    - Compatibilité avec analysis/pipeline.py

TIMEFRAMES :
    D1  -> 1day
    H4  -> 4h
    H1  -> 1h
    M15 -> 15min
    M5  -> 5min
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

import requests

from core.models import Candle


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://api.twelvedata.com/time_series"

TIMEFRAME_MAP = {
    "D1": "1day",
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}

VALID_TIMEFRAMES = set(
    TIMEFRAME_MAP.keys()
)

REQUEST_TIMEOUT = 15

# Nombre maximum de tentatives pour une erreur temporaire.
MAX_RETRIES = 3

# Délais entre les tentatives classiques.
RETRY_DELAYS = (
    5,
    15,
    30,
)

# ------------------------------------------------------------
# CACHE
# ------------------------------------------------------------

# Cache principal.
#
# Les bougies H4/H1/M15 changent beaucoup moins rapidement
# que M5. On peut donc les conserver plus longtemps.
CACHE_TTL_SECONDS = {
    "D1": 900,      # 15 minutes
    "H4": 600,      # 10 minutes
    "H1": 300,      # 5 minutes
    "M15": 120,     # 2 minutes
    "M5": 60,       # 1 minute
}

# Durée maximale pendant laquelle des données précédemment
# valides peuvent être utilisées lorsqu'une limitation API
# temporaire est active.
STALE_CACHE_MAX_AGE_SECONDS = {
    "D1": 7200,     # 2 heures
    "H4": 3600,     # 1 heure
    "H1": 1800,     # 30 minutes
    "M15": 900,     # 15 minutes
    "M5": 300,      # 5 minutes
}

# Cooldown global après HTTP 429.
DEFAULT_RATE_LIMIT_COOLDOWN = 60

# Ne jamais attendre des heures dans le processus.
MAX_RATE_LIMIT_COOLDOWN = 300

# Nombre maximum d'entrées du cache.
MAX_CACHE_ENTRIES = 500

_CACHE_LOCK = Lock()

# {
#   cache_key: {
#       "candles": list[Candle],
#       "saved_at": float,
#       "last_success": float,
#   }
# }
_CANDLE_CACHE: dict[
    tuple[str, str, int],
    dict,
] = {}

# Dernier moment où Twelve Data a renvoyé 429.
_RATE_LIMIT_UNTIL = 0.0

# Dernier message 429.
_RATE_LIMIT_MESSAGE = ""


# ============================================================
# STATISTIQUES
# ============================================================

@dataclass
class MarketDataStats:

    requests_total: int = 0
    requests_success: int = 0

    rate_limit_count: int = 0

    cache_hits: int = 0
    stale_cache_hits: int = 0
    cache_misses: int = 0

    errors: int = 0


_STATS = MarketDataStats()


# ============================================================
# API KEY
# ============================================================

def _get_api_key() -> str:

    api_key = os.getenv(
        "TWELVE_DATA_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY est absente "
            "des variables d'environnement."
        )

    return api_key.strip()


# ============================================================
# TIMEFRAME
# ============================================================

def _normalize_timeframe(
    timeframe: str,
) -> str:

    normalized = str(
        timeframe
    ).upper().strip()

    if normalized not in VALID_TIMEFRAMES:

        raise ValueError(
            "Timeframe invalide : "
            f"{timeframe}. "
            "Valeurs autorisées : "
            f"{sorted(VALID_TIMEFRAMES)}"
        )

    return normalized


# ============================================================
# SYMBOL
# ============================================================

def _normalize_symbol(
    symbol: str,
) -> str:

    normalized = str(
        symbol
    ).upper().strip()

    if not normalized:
        raise ValueError(
            "Symbole vide."
        )

    return normalized


# ============================================================
# TIMESTAMP
# ============================================================

def _parse_timestamp(
    value: str,
) -> datetime:

    text = str(value).strip()

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )

    for fmt in formats:

        try:

            parsed = datetime.strptime(
                text,
                fmt,
            )

            return parsed.replace(
                tzinfo=timezone.utc
            )

        except ValueError:
            continue

    raise ValueError(
        f"Timestamp Twelve Data invalide : {value}"
    )


# ============================================================
# API ERROR
# ============================================================

def _parse_api_error(
    response: requests.Response,
) -> str:

    try:

        data = response.json()

    except Exception:

        return (
            f"HTTP {response.status_code}"
        )

    if isinstance(data, dict):

        message = data.get(
            "message"
        )

        code = data.get(
            "code"
        )

        if message and code:

            return (
                f"{message} "
                f"(code {code})"
            )

        if message:
            return str(message)

    return (
        f"HTTP {response.status_code}"
    )


# ============================================================
# RATE LIMIT
# ============================================================

def _set_rate_limit(
    retry_after: Optional[int] = None,
) -> None:

    global _RATE_LIMIT_UNTIL
    global _RATE_LIMIT_MESSAGE

    now = time.time()

    delay = (
        retry_after
        if retry_after is not None
        else DEFAULT_RATE_LIMIT_COOLDOWN
    )

    try:
        delay = int(delay)
    except (TypeError, ValueError):
        delay = DEFAULT_RATE_LIMIT_COOLDOWN

    delay = max(
        1,
        min(
            delay,
            MAX_RATE_LIMIT_COOLDOWN,
        ),
    )

    with _CACHE_LOCK:

        _RATE_LIMIT_UNTIL = max(
            _RATE_LIMIT_UNTIL,
            now + delay,
        )

        _RATE_LIMIT_MESSAGE = (
            "Limite Twelve Data active. "
            f"Nouvelle tentative dans environ {delay}s."
        )

        _STATS.rate_limit_count += 1


def _rate_limit_remaining() -> int:

    with _CACHE_LOCK:

        remaining = (
            _RATE_LIMIT_UNTIL
            - time.time()
        )

    if remaining <= 0:
        return 0

    return int(
        remaining + 0.999
    )


def _rate_limit_active() -> bool:

    return (
        _rate_limit_remaining()
        > 0
    )


# ============================================================
# CACHE KEY
# ============================================================

def _cache_key(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> tuple[str, str, int]:

    return (
        symbol.upper(),
        timeframe.upper(),
        int(outputsize),
    )


# ============================================================
# CACHE READ
# ============================================================

def _get_cached_candles(
    key: tuple[str, str, int],
    timeframe: str,
    allow_stale: bool = False,
) -> Optional[list[Candle]]:

    now = time.time()

    with _CACHE_LOCK:

        item = _CANDLE_CACHE.get(
            key
        )

        if not item:
            _STATS.cache_misses += 1
            return None

        saved_at = float(
            item.get(
                "saved_at",
                0.0,
            )
        )

        candles = item.get(
            "candles"
        )

        if not candles:
            _STATS.cache_misses += 1
            return None

        age = now - saved_at

        ttl = CACHE_TTL_SECONDS[
            timeframe
        ]

        if age <= ttl:

            _STATS.cache_hits += 1

            return list(candles)

        if allow_stale:

            max_age = (
                STALE_CACHE_MAX_AGE_SECONDS[
                    timeframe
                ]
            )

            if age <= max_age:

                _STATS.stale_cache_hits += 1

                return list(candles)

        _STATS.cache_misses += 1

        return None


# ============================================================
# CACHE WRITE
# ============================================================

def _save_cache(
    key: tuple[str, str, int],
    candles: list[Candle],
) -> None:

    now = time.time()

    with _CACHE_LOCK:

        _CANDLE_CACHE[key] = {
            "candles": list(candles),
            "saved_at": now,
            "last_success": now,
        }

        # ----------------------------------------------------
        # Nettoyage simple si le cache devient trop gros.
        # ----------------------------------------------------

        if len(_CANDLE_CACHE) > MAX_CACHE_ENTRIES:

            oldest_key = min(
                _CANDLE_CACHE,
                key=lambda cache_key:
                _CANDLE_CACHE[
                    cache_key
                ].get(
                    "saved_at",
                    0.0,
                ),
            )

            _CANDLE_CACHE.pop(
                oldest_key,
                None,
            )


# ============================================================
# PARSING DES BOUGIES
# ============================================================

def _parse_candles(
    data: dict,
) -> list[Candle]:

    values = data.get(
        "values"
    )

    if not isinstance(
        values,
        list,
    ):
        raise RuntimeError(
            "Réponse Twelve Data sans "
            "liste 'values'."
        )

    candles: list[Candle] = []

    for item in values:

        if not isinstance(
            item,
            dict,
        ):
            continue

        timestamp = item.get(
            "datetime"
        )

        if timestamp is None:
            continue

        try:

            candle = Candle(
                timestamp=_parse_timestamp(
                    timestamp
                ),
                open=float(
                    item["open"]
                ),
                high=float(
                    item["high"]
                ),
                low=float(
                    item["low"]
                ),
                close=float(
                    item["close"]
                ),
                volume=float(
                    item.get(
                        "volume",
                        0.0,
                    )
                    or 0.0
                ),
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):

            continue

        candles.append(
            candle
        )

    if not candles:

        raise RuntimeError(
            "Twelve Data a renvoyé "
            "0 bougie exploitable."
        )

    # Twelve Data renvoie généralement
    # la plus récente en premier.
    #
    # Le pipeline NOVA TRADE AI travaille
    # dans l'ordre chronologique.
    candles.sort(
        key=lambda candle:
        candle.timestamp
    )

    return candles


# ============================================================
# HTTP REQUEST
# ============================================================

def _request_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> list[Candle]:

    api_key = _get_api_key()

    interval = TIMEFRAME_MAP[
        timeframe
    ]

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
    }

    last_error: Optional[Exception] = None

    for attempt in range(
        MAX_RETRIES + 1
    ):

        _STATS.requests_total += 1

        try:

            response = requests.get(
                BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

        except requests.RequestException as exc:

            last_error = exc
            _STATS.errors += 1

            if attempt >= MAX_RETRIES:
                break

            delay = RETRY_DELAYS[
                min(
                    attempt,
                    len(RETRY_DELAYS) - 1,
                )
            ]

            time.sleep(delay)
            continue

        # ====================================================
        # RATE LIMIT
        # ====================================================

        if response.status_code == 429:

            retry_after = (
                response.headers.get(
                    "Retry-After"
                )
            )

            retry_seconds = None

            if retry_after:

                try:
                    retry_seconds = int(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    retry_seconds = None

            _set_rate_limit(
                retry_seconds
            )

            last_error = RuntimeError(
                "Limite Twelve Data active."
            )

            # ------------------------------------------------
            # IMPORTANT :
            # On ne multiplie pas les requêtes pendant
            # le rate limit.
            # ------------------------------------------------

            if attempt >= MAX_RETRIES:
                break

            remaining = _rate_limit_remaining()

            # Attente limitée.
            wait_time = min(
                max(remaining, 1),
                MAX_RATE_LIMIT_COOLDOWN,
            )

            time.sleep(
                wait_time
            )

            continue

        # ====================================================
        # ERREURS 5XX
        # ====================================================

        if response.status_code >= 500:

            message = _parse_api_error(
                response
            )

            last_error = RuntimeError(
                message
            )

            _STATS.errors += 1

            if attempt >= MAX_RETRIES:
                break

            delay = RETRY_DELAYS[
                min(
                    attempt,
                    len(RETRY_DELAYS) - 1,
                )
            ]

            time.sleep(delay)
            continue

        # ====================================================
        # ERREURS 4XX
        # ====================================================

        if response.status_code >= 400:

            message = _parse_api_error(
                response
            )

            raise RuntimeError(
                f"Twelve Data HTTP "
                f"{response.status_code} : "
                f"{message}"
            )

        # ====================================================
        # JSON
        # ====================================================

        try:

            data = response.json()

        except ValueError as exc:

            last_error = RuntimeError(
                "Réponse Twelve Data "
                "non JSON."
            )

            _STATS.errors += 1

            if attempt >= MAX_RETRIES:
                break

            time.sleep(
                RETRY_DELAYS[
                    min(
                        attempt,
                        len(RETRY_DELAYS) - 1,
                    )
                ]
            )

            continue

        # ====================================================
        # ERREUR API DANS HTTP 200
        # ====================================================

        if isinstance(
            data,
            dict,
        ):

            status = str(
                data.get(
                    "status",
                    ""
                )
            ).lower()

            if status == "error":

                message = data.get(
                    "message",
                    "Erreur Twelve Data.",
                )

                code = data.get(
                    "code"
                )

                if code:

                    message = (
                        f"{message} "
                        f"(code {code})"
                    )

                raise RuntimeError(
                    str(message)
                )

        # ====================================================
        # PARSING
        # ====================================================

        try:

            candles = _parse_candles(
                data
            )

        except Exception as exc:

            last_error = exc
            _STATS.errors += 1

            if attempt >= MAX_RETRIES:
                break

            time.sleep(
                RETRY_DELAYS[
                    min(
                        attempt,
                        len(RETRY_DELAYS) - 1,
                    )
                ]
            )

            continue

        # ====================================================
        # SUCCESS
        # ====================================================

        _STATS.requests_success += 1

        return candles

    if last_error:

        raise last_error

    raise RuntimeError(
        "Échec de récupération des "
        "données Twelve Data."
    )


# ============================================================
# GET CANDLES
# ============================================================

def get_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 100,
) -> list[Candle]:

    symbol = _normalize_symbol(
        symbol
    )

    timeframe = _normalize_timeframe(
        timeframe
    )

    try:

        outputsize = int(
            outputsize
        )

    except (
        TypeError,
        ValueError,
    ):

        raise ValueError(
            "outputsize doit être un entier."
        )

    if outputsize <= 0:
        raise ValueError(
            "outputsize doit être supérieur à 0."
        )

    key = _cache_key(
        symbol,
        timeframe,
        outputsize,
    )

    # ========================================================
    # 1. CACHE FRAIS
    # ========================================================

    cached = _get_cached_candles(
        key,
        timeframe,
        allow_stale=False,
    )

    if cached is not None:
        return cached

    # ========================================================
    # 2. RATE LIMIT GLOBAL
    # ========================================================

    if _rate_limit_active():

        stale = _get_cached_candles(
            key,
            timeframe,
            allow_stale=True,
        )

        if stale is not None:
            return stale

        remaining = (
            _rate_limit_remaining()
        )

        raise RuntimeError(
            "Limite Twelve Data active "
            "et aucune donnée récente en "
            f"cache pour {symbol} "
            f"{timeframe}. "
            f"Réessayer dans environ "
            f"{remaining}s."
        )

    # ========================================================
    # 3. REQUÊTE API
    # ========================================================

    try:

        candles = _request_candles(
            symbol,
            timeframe,
            outputsize,
        )

    except Exception as exc:

        # ----------------------------------------------------
        # Si Twelve Data devient temporairement indisponible,
        # on tente une dernière fois le cache périmé.
        # ----------------------------------------------------

        stale = _get_cached_candles(
            key,
            timeframe,
            allow_stale=True,
        )

        if stale is not None:
            return stale

        raise exc

    # ========================================================
    # 4. CACHE
    # ========================================================

    _save_cache(
        key,
        candles,
    )

    return candles


# ============================================================
# DERNIER PRIX
# ============================================================

def get_latest_price(
    symbol: str,
) -> float:

    candles = get_candles(
        symbol,
        "M5",
        outputsize=2,
    )

    if not candles:
        raise RuntimeError(
            f"Aucun prix disponible pour {symbol}."
        )

    return float(
        candles[-1].close
    )


# ============================================================
# CACHE MANUEL
# ============================================================

def clear_cache() -> None:

    global _RATE_LIMIT_UNTIL
    global _RATE_LIMIT_MESSAGE

    with _CACHE_LOCK:

        _CANDLE_CACHE.clear()

        _RATE_LIMIT_UNTIL = 0.0
        _RATE_LIMIT_MESSAGE = ""


def clear_symbol_cache(
    symbol: str,
) -> None:

    symbol = _normalize_symbol(
        symbol
    )

    with _CACHE_LOCK:

        keys_to_delete = [
            key
            for key in _CANDLE_CACHE
            if key[0] == symbol
        ]

        for key in keys_to_delete:

            _CANDLE_CACHE.pop(
                key,
                None,
            )


# ============================================================
# STATISTIQUES
# ============================================================

def get_market_data_stats() -> dict:

    with _CACHE_LOCK:

        cache_entries = len(
            _CANDLE_CACHE
        )

        rate_limit_remaining = (
            _rate_limit_remaining()
        )

    return {
        "requests_total":
            _STATS.requests_total,

        "requests_success":
            _STATS.requests_success,

        "rate_limit_count":
            _STATS.rate_limit_count,

        "cache_hits":
            _STATS.cache_hits,

        "stale_cache_hits":
            _STATS.stale_cache_hits,

        "cache_misses":
            _STATS.cache_misses,

        "errors":
            _STATS.errors,

        "cache_entries":
            cache_entries,

        "rate_limit_remaining":
            rate_limit_remaining,
    }


# ============================================================
# COMPATIBILITÉ
# ============================================================

def get_price(
    symbol: str,
) -> float:

    return get_latest_price(
        symbol
    )