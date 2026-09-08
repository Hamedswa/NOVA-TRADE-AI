"""
NOVA TRADE AI
market_data.py

Architecture stricte :

FOREX + XAU/USD
    -> Twelve Data uniquement

CRYPTO
    -> Binance uniquement
    -> Aucun fallback Twelve Data

Cache :
    H4  -> 8 heures
    H1  -> 2 heures
    M15 -> 30 minutes
    M5  -> 1 minute

Objectifs :
    - réduire fortement les appels Twelve Data
    - ne jamais utiliser Twelve Data pour la crypto
    - réutiliser les données en cache
    - gérer proprement les limites API
    - conserver les données anciennes en cas d'erreur temporaire
"""

import os
import sys
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.models import Candle


# ============================================================
# URL API
# ============================================================

TWELVE_DATA_URL = (
    "https://api.twelvedata.com/time_series"
)

BINANCE_KLINES_URL = (
    "https://api.binance.com/api/v3/klines"
)


# ============================================================
# CONFIGURATION REQUÊTES
# ============================================================

TWELVE_TIMEOUT = 15
BINANCE_TIMEOUT = 10

TWELVE_MAX_RETRIES = 3
BINANCE_MAX_RETRIES = 3

TWELVE_RETRY_DELAYS = (5, 15, 30)
BINANCE_RETRY_DELAYS = (2, 5, 10)


# ============================================================
# TIMEFRAMES
# ============================================================

TIMEFRAME_MAP = {
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}

BINANCE_INTERVAL_MAP = {
    "H4": "4h",
    "H1": "1h",
    "M15": "15m",
    "M5": "5m",
}


# ============================================================
# CACHE
# ============================================================

CACHE_TTL = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 60,
}


# Âge maximal accepté pour utiliser des données
# anciennes en cas d'erreur API.
STALE_MAX_AGE = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 5 * 60,
}


# ============================================================
# PROTECTION TWELVE DATA
# ============================================================

TWELVE_MIN_REQUEST_INTERVAL = 2.0

_last_twelve_request = 0.0

_rate_lock = Lock()
_cache_lock = Lock()


# ============================================================
# CACHE INTERNE
# ============================================================

_candle_cache: Dict[
    Tuple[str, str],
    Dict[str, Any],
] = {}


# ============================================================
# ÉTAT DES LIMITES API
# ============================================================

# Lorsque Twelve Data indique que le quota journalier
# est épuisé, on arrête immédiatement de l'appeler.
#
# Cela évite :
#
# 800 crédits
#      ↓
# quota atteint
#      ↓
# appels inutiles
#      ↓
# 1400+ crédits consommés
#
# Le verrou est conservateur : 24 heures.

_twelve_daily_block_until = 0.0

_twelve_daily_block_lock = Lock()


# ============================================================
# STATISTIQUES
# ============================================================

_stats = {
    "cache_hits": 0,
    "cache_misses": 0,
    "twelve_requests": 0,
    "twelve_errors": 0,
    "twelve_daily_blocks": 0,
    "binance_requests": 0,
    "binance_errors": 0,
    "binance_unavailable": 0,
}


# ============================================================
# CRYPTO -> BINANCE
# ============================================================

CRYPTO_SYMBOL_MAP = {
    "BTC/USD": "BTCUSDT",
    "ETH/USD": "ETHUSDT",
    "SOL/USD": "SOLUSDT",
    "BNB/USD": "BNBUSDT",
    "XRP/USD": "XRPUSDT",
}


# ============================================================
# NORMALISATION
# ============================================================

def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _normalize_timeframe(
    timeframe: str,
) -> str:

    tf = str(timeframe or "").strip().upper()

    aliases = {
        "4H": "H4",
        "1H": "H1",
        "15M": "M15",
        "5M": "M5",
        "15MIN": "M15",
        "5MIN": "M5",
        "60MIN": "H1",
        "240MIN": "H4",
    }

    tf = aliases.get(tf, tf)

    if tf not in TIMEFRAME_MAP:
        raise ValueError(
            f"Timeframe invalide : {timeframe}. "
            f"Valeurs autorisées : "
            f"{list(TIMEFRAME_MAP.keys())}"
        )

    return tf


def _is_crypto_symbol(
    symbol: str,
) -> bool:

    return (
        _normalize_symbol(symbol)
        in CRYPTO_SYMBOL_MAP
    )


# ============================================================
# CLÉS API
# ============================================================

def _get_twelve_data_api_key() -> Optional[str]:

    return (
        os.getenv("TWELVE_DATA_API_KEY")
        or os.getenv("TWELVE_DATA_KEY")
    )


def _get_binance_api_key() -> Optional[str]:

    return os.getenv(
        "BINANCE_API_KEY"
    )


def _get_binance_api_secret() -> Optional[str]:

    return os.getenv(
        "BINANCE_API_SECRET"
    )


# ============================================================
# DATE / HEURE
# ============================================================

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_to_datetime(
    value: Any,
) -> datetime:

    if isinstance(value, datetime):

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    text = str(value).strip()

    if text.endswith("Z"):
        text = (
            text[:-1]
            + "+00:00"
        )

    try:

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        pass

    try:

        return datetime.fromtimestamp(
            float(value),
            tz=timezone.utc,
        )

    except Exception:

        return _utc_now()


# ============================================================
# CACHE
# ============================================================

def _cache_key(
    symbol: str,
    timeframe: str,
) -> Tuple[str, str]:

    return (
        _normalize_symbol(symbol),
        _normalize_timeframe(timeframe),
    )


def _get_cached_candles(
    symbol: str,
    timeframe: str,
) -> Optional[List[Candle]]:

    key = _cache_key(
        symbol,
        timeframe,
    )

    now = time.time()

    with _cache_lock:

        item = _candle_cache.get(key)

        if not item:

            _stats["cache_misses"] += 1

            return None

        created_at = float(
            item.get(
                "created_at",
                0,
            )
        )

        candles = item.get(
            "candles"
        )

        if not candles:

            _stats["cache_misses"] += 1

            return None

        age = now - created_at

        ttl = CACHE_TTL[
            timeframe
        ]

        # ----------------------------------------------------
        # CACHE VALIDE
        # ----------------------------------------------------

        if age < ttl:

            _stats["cache_hits"] += 1

            return list(candles)

        # ----------------------------------------------------
        # CACHE EXPIRÉ MAIS ENCORE UTILISABLE
        # ----------------------------------------------------

        if age < STALE_MAX_AGE[
            timeframe
        ]:

            return list(candles)

        _stats["cache_misses"] += 1

        return None


def _get_stale_cache(
    symbol: str,
    timeframe: str,
) -> Optional[List[Candle]]:

    key = _cache_key(
        symbol,
        timeframe,
    )

    with _cache_lock:

        item = _candle_cache.get(key)

        if not item:
            return None

        candles = item.get(
            "candles"
        )

        if not candles:
            return None

        return list(candles)


def _set_cached_candles(
    symbol: str,
    timeframe: str,
    candles: List[Candle],
) -> None:

    key = _cache_key(
        symbol,
        timeframe,
    )

    with _cache_lock:

        _candle_cache[key] = {
            "candles": list(candles),
            "created_at": time.time(),
        }


def clear_cache() -> None:

    with _cache_lock:

        _candle_cache.clear()


# ============================================================
# VERROU QUOTA TWELVE DATA
# ============================================================

def _is_twelve_daily_blocked() -> bool:

    with _twelve_daily_block_lock:

        return (
            time.time()
            < _twelve_daily_block_until
        )


def _block_twelve_for_day() -> None:

    global _twelve_daily_block_until

    with _twelve_daily_block_lock:

        # 24 heures.
        _twelve_daily_block_until = (
            time.time()
            + 24 * 60 * 60
        )

        _stats[
            "twelve_daily_blocks"
        ] += 1


# ============================================================
# RATE LIMIT TWELVE DATA
# ============================================================

def _wait_for_twelve_rate_limit() -> None:

    global _last_twelve_request

    with _rate_lock:

        now = time.monotonic()

        elapsed = (
            now
            - _last_twelve_request
        )

        if (
            elapsed
            < TWELVE_MIN_REQUEST_INTERVAL
        ):

            wait_time = (
                TWELVE_MIN_REQUEST_INTERVAL
                - elapsed
            )

            time.sleep(
                wait_time
            )

        _last_twelve_request = (
            time.monotonic()
        )


# ============================================================
# ERREUR API
# ============================================================

def _extract_api_error(
    response: requests.Response,
) -> str:

    try:

        data = response.json()

        if isinstance(
            data,
            dict,
        ):

            if data.get(
                "message"
            ):

                return str(
                    data["message"]
                )

            if (
                data.get("status")
                == "error"
            ):

                return str(
                    data.get(
                        "message",
                        "Erreur API inconnue",
                    )
                )

    except Exception:
        pass

    return (
        f"HTTP {response.status_code}: "
        f"{response.text[:300]}"
    )


# ============================================================
# DÉTECTION QUOTA TWELVE DATA
# ============================================================

def _is_twelve_quota_error(
    message: str,
) -> bool:

    text = str(
        message or ""
    ).lower()

    indicators = (
        "run out of api credits",
        "api credits for the day",
        "daily limit",
        "current limit",
        "credits were used",
        "quota",
        "you have run out",
    )

    return any(
        indicator in text
        for indicator in indicators
    )


# ============================================================
# TWELVE DATA
# ============================================================

def _request_twelve_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> List[Candle]:

    # --------------------------------------------------------
    # VÉRIFICATION QUOTA
    # --------------------------------------------------------

    if _is_twelve_daily_blocked():

        raise RuntimeError(
            "Twelve Data temporairement "
            "bloqué : quota journalier atteint."
        )

    api_key = (
        _get_twelve_data_api_key()
    )

    if not api_key:

        raise RuntimeError(
            "TWELVE_DATA_API_KEY "
            "non configurée."
        )

    interval = TIMEFRAME_MAP[
        timeframe
    ]

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
    }

    last_error = None

    for attempt in range(
        TWELVE_MAX_RETRIES
    ):

        try:

            _wait_for_twelve_rate_limit()

            _stats[
                "twelve_requests"
            ] += 1

            response = requests.get(
                TWELVE_DATA_URL,
                params=params,
                timeout=TWELVE_TIMEOUT,
            )

            if (
                response.status_code
                != 200
            ):

                error = (
                    _extract_api_error(
                        response
                    )
                )

                if _is_twelve_quota_error(
                    error
                ):

                    _block_twelve_for_day()

                    raise RuntimeError(
                        "Twelve Data : "
                        + error
                    )

                raise RuntimeError(
                    error
                )

            data = response.json()

            if data.get(
                "status"
            ) == "error":

                error = str(
                    data.get(
                        "message",
                        "Erreur Twelve Data",
                    )
                )

                if _is_twelve_quota_error(
                    error
                ):

                    _block_twelve_for_day()

                    raise RuntimeError(
                        "Twelve Data : "
                        + error
                    )

                raise RuntimeError(
                    error
                )

            values = data.get(
                "values",
                [],
            )

            if not values:

                raise RuntimeError(
                    "Twelve Data "
                    "n'a retourné aucun "
                    "chandelier."
                )

            candles: List[
                Candle
            ] = []

            for item in reversed(
                values
            ):

                try:

                    candles.append(
                        Candle(
                            timestamp=(
                                _timestamp_to_datetime(
                                    item.get(
                                        "datetime"
                                    )
                                )
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
                                    0,
                                )
                                or 0
                            ),
                        )
                    )

                except Exception:
                    continue

            if not candles:

                raise RuntimeError(
                    "Impossible de "
                    "convertir les "
                    "chandeliers "
                    "Twelve Data."
                )

            return candles

        except Exception as exc:

            last_error = exc

            _stats[
                "twelve_errors"
            ] += 1

            # ------------------------------------------------
            # SI QUOTA JOURNALIER :
            # ARRÊT IMMÉDIAT
            # ------------------------------------------------

            if _is_twelve_quota_error(
                str(exc)
            ):

                _block_twelve_for_day()

                raise RuntimeError(
                    str(exc)
                )

            if attempt < (
                TWELVE_MAX_RETRIES - 1
            ):

                delay = (
                    TWELVE_RETRY_DELAYS[
                        min(
                            attempt,
                            len(
                                TWELVE_RETRY_DELAYS
                            ) - 1,
                        )
                    ]
                )

                time.sleep(
                    delay
                )

    raise RuntimeError(
        f"Twelve Data : "
        f"{last_error}"
    )


# ============================================================
# BINANCE
# ============================================================

def _request_binance_candles(
    symbol: str,
    timeframe: str,
    limit: int = 300,
) -> List[Candle]:

    symbol = _normalize_symbol(
        symbol
    )

    binance_symbol = (
        CRYPTO_SYMBOL_MAP.get(
            symbol
        )
    )

    if not binance_symbol:

        raise ValueError(
            f"Symbole crypto Binance "
            f"inconnu : {symbol}"
        )

    interval = (
        BINANCE_INTERVAL_MAP[
            timeframe
        ]
    )

    params = {
        "symbol": binance_symbol,
        "interval": interval,
        "limit": min(
            int(limit),
            1000,
        ),
    }

    last_error = None

    for attempt in range(
        BINANCE_MAX_RETRIES
    ):

        try:

            _stats[
                "binance_requests"
            ] += 1

            response = requests.get(
                BINANCE_KLINES_URL,
                params=params,
                timeout=BINANCE_TIMEOUT,
            )

            if (
                response.status_code
                != 200
            ):

                raise RuntimeError(
                    _extract_api_error(
                        response
                    )
                )

            data = response.json()

            if (
                not isinstance(
                    data,
                    list,
                )
                or not data
            ):

                raise RuntimeError(
                    "Binance n'a retourné "
                    "aucun chandelier."
                )

            candles: List[
                Candle
            ] = []

            for item in data:

                try:

                    timestamp_ms = int(
                        item[0]
                    )

                    candles.append(
                        Candle(
                            timestamp=(
                                datetime.fromtimestamp(
                                    timestamp_ms
                                    / 1000,
                                    tz=timezone.utc,
                                )
                            ),
                            open=float(
                                item[1]
                            ),
                            high=float(
                                item[2]
                            ),
                            low=float(
                                item[3]
                            ),
                            close=float(
                                item[4]
                            ),
                            volume=float(
                                item[5]
                            ),
                        )
                    )

                except Exception:
                    continue

            if not candles:

                raise RuntimeError(
                    "Impossible de "
                    "convertir les "
                    "chandeliers Binance."
                )

            return candles

        except Exception as exc:

            last_error = exc

            _stats[
                "binance_errors"
            ] += 1

            if attempt < (
                BINANCE_MAX_RETRIES - 1
            ):

                delay = (
                    BINANCE_RETRY_DELAYS[
                        min(
                            attempt,
                            len(
                                BINANCE_RETRY_DELAYS
                            ) - 1,
                        )
                    ]
                )

                time.sleep(
                    delay
                )

    raise RuntimeError(
        f"Binance : "
        f"{last_error}"
    )


# ============================================================
# ROUTAGE DES DONNÉES
# ============================================================

def _request_market_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> List[Candle]:

    symbol = _normalize_symbol(
        symbol
    )

    timeframe = _normalize_timeframe(
        timeframe
    )

    # ========================================================
    # CRYPTO
    # ========================================================

    if _is_crypto_symbol(
        symbol
    ):

        # IMPORTANT :
        #
        # CRYPTO -> BINANCE UNIQUEMENT
        #
        # Aucun fallback Twelve Data.
        #

        return _request_binance_candles(
            symbol,
            timeframe,
            outputsize,
        )

    # ========================================================
    # FOREX + XAU
    # ========================================================

    return _request_twelve_candles(
        symbol,
        timeframe,
        outputsize,
    )


# ============================================================
# FONCTION PRINCIPALE
# ============================================================

def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 300,
    force_refresh: bool = False,
) -> List[Candle]:

    symbol = _normalize_symbol(
        symbol
    )

    timeframe = _normalize_timeframe(
        timeframe
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if not force_refresh:

        cached = (
            _get_cached_candles(
                symbol,
                timeframe,
            )
        )

        if cached:

            return cached[
                -limit:
            ]

    # --------------------------------------------------------
    # DONNÉES API
    # --------------------------------------------------------

    try:

        candles = (
            _request_market_candles(
                symbol,
                timeframe,
                max(
                    int(limit),
                    300,
                ),
            )
        )

        if candles:

            _set_cached_candles(
                symbol,
                timeframe,
                candles,
            )

            return candles[
                -limit:
            ]

    except Exception:

        # ----------------------------------------------------
        # IMPORTANT :
        # On ne tente PAS Twelve Data après Binance
        # pour une crypto.
        # ----------------------------------------------------

        stale = _get_stale_cache(
            symbol,
            timeframe,
        )

        if stale:

            return stale[
                -limit:
            ]

        raise

    return []


# ============================================================
# DERNIER PRIX
# ============================================================

def get_latest_price(
    symbol: str,
) -> Optional[float]:

    symbol = _normalize_symbol(
        symbol
    )

    try:

        candles = get_candles(
            symbol,
            "M5",
            limit=2,
        )

        if candles:

            return float(
                candles[-1].close
            )

    except Exception:
        pass

    return None


def get_price(
    symbol: str,
) -> Optional[float]:

    return get_latest_price(
        symbol
    )


# ============================================================
# INFORMATIONS SOURCE
# ============================================================

def get_data_source(
    symbol: str,
) -> str:

    symbol = _normalize_symbol(
        symbol
    )

    if _is_crypto_symbol(
        symbol
    ):

        return "BINANCE"

    return "TWELVE_DATA"


# ============================================================
# VÉRIFICATION SOURCE
# ============================================================

def is_crypto(
    symbol: str,
) -> bool:

    return _is_crypto_symbol(
        symbol
    )


# ============================================================
# STATUT TWELVE DATA
# ============================================================

def is_twelve_data_blocked() -> bool:

    return _is_twelve_daily_blocked()


# ============================================================
# STATISTIQUES
# ============================================================

def get_stats() -> Dict[str, Any]:

    with _cache_lock:

        stats = dict(
            _stats
        )

        stats[
            "cache_entries"
        ] = len(
            _candle_cache
        )

        stats[
            "cached_symbols"
        ] = sorted(
            {
                key[0]
                for key in
                _candle_cache.keys()
            }
        )

        stats[
            "twelve_data_blocked"
        ] = (
            _is_twelve_daily_blocked()
        )

        return stats


def reset_stats() -> None:

    with _cache_lock:

        for key in _stats:

            _stats[key] = 0


# ============================================================
# OBJET MODULE
# ============================================================

# Permet au pipeline d'utiliser :
#
# from market_data import market_data
#
# puis :
#
# market_data.get_candles(...)

market_data = sys.modules[
    __name__
]