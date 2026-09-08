"""
NOVA TRADE AI
market_data.py

MOTEUR CENTRAL DES DONNÉES DE MARCHÉ

Architecture :

    FOREX / XAU
        ↓
    Twelve Data
        ↓
    Cache intelligent

    CRYPTO
        ↓
    Binance
        ↓
    Cache intelligent
        ↓
    Twelve Data = fallback

Timeframes :
    H4  → refresh toutes les 8 heures
    H1  → refresh toutes les 2 heures
    M15 → refresh toutes les 30 minutes
    M5  → refresh toutes les 1 minute

D1 n'est PAS utilisé par NOVA TRADE AI.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional, Tuple

import requests

from core.models import Candle


# ============================================================
# TWELVE DATA
# ============================================================

TWELVE_DATA_URL = (
    "https://api.twelvedata.com/time_series"
)

TWELVE_REQUEST_TIMEOUT = 15

TWELVE_MAX_RETRIES = 3

TWELVE_RETRY_DELAYS = (
    5,
    15,
    30,
)


# ============================================================
# BINANCE
# ============================================================

BINANCE_KLINES_URL = (
    "https://api.binance.com/api/v3/klines"
)

BINANCE_REQUEST_TIMEOUT = 10

BINANCE_MAX_RETRIES = 3

BINANCE_RETRY_DELAYS = (
    2,
    5,
    10,
)


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

VALID_TIMEFRAMES = set(
    TIMEFRAME_MAP.keys()
)


# ============================================================
# CACHE TTL
# ============================================================

# Temps pendant lequel une donnée est considérée
# comme suffisamment récente pour être réutilisée.
#
# H4  : 8 heures
# H1  : 2 heures
# M15 : 30 minutes
# M5  : 1 minute
CACHE_TTL_SECONDS = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 60,
}


# ============================================================
# CACHE STALE
# ============================================================

# Une donnée expirée peut exceptionnellement être
# utilisée comme secours si l'API est temporairement
# indisponible.
#
# On reste volontairement strict.
STALE_CACHE_MAX_AGE_SECONDS = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 5 * 60,
}


_CACHE_LOCK = Lock()

# key :
# (SYMBOL, TIMEFRAME, OUTPUTSIZE)
#
# value :
# {
#     "candles": [...],
#     "timestamp": float
# }
_CANDLE_CACHE: Dict[
    Tuple[str, str, int],
    Dict[str, object],
] = {}


# ============================================================
# RATE LIMIT TWELVE DATA
# ============================================================

_RATE_LIMIT_LOCK = Lock()

_RATE_LIMIT_UNTIL = 0.0


# ============================================================
# RATE LIMIT BINANCE
# ============================================================

_BINANCE_RATE_LIMIT_LOCK = Lock()

_BINANCE_RATE_LIMIT_UNTIL = 0.0


# ============================================================
# STATISTIQUES
# ============================================================

_STATS_LOCK = Lock()

_STATS = {
    "api_requests": 0,

    "twelve_requests": 0,
    "binance_requests": 0,

    "successful_requests": 0,

    "twelve_successful_requests": 0,
    "binance_successful_requests": 0,

    "cache_hits": 0,
    "stale_cache_hits": 0,

    "twelve_rate_limit_hits": 0,
    "binance_rate_limit_hits": 0,

    "fallback_to_twelve": 0,

    "errors": 0,
}


# ============================================================
# SYMBOLES CRYPTO
# ============================================================

CRYPTO_SYMBOLS = {
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "BNB/USD",
    "XRP/USD",
}


# ============================================================
# MAPPING CRYPTO -> BINANCE
# ============================================================

BINANCE_SYMBOL_MAP = {
    "BTC/USD": "BTCUSDT",
    "ETH/USD": "ETHUSDT",
    "SOL/USD": "SOLUSDT",
    "BNB/USD": "BNBUSDT",
    "XRP/USD": "XRPUSDT",
}


# ============================================================
# API KEY TWELVE DATA
# ============================================================

def _get_twelve_data_api_key() -> str:
    """
    Récupère la clé Twelve Data.

    Variable Railway :
        TWELVE_DATA_API_KEY
    """

    key = os.getenv(
        "TWELVE_DATA_API_KEY",
        "",
    ).strip()

    if not key:
        raise RuntimeError(
            "Variable d'environnement "
            "TWELVE_DATA_API_KEY absente."
        )

    return key


# ============================================================
# API KEY BINANCE
# ============================================================

def _get_binance_api_key() -> str:
    """
    Récupère éventuellement la clé Binance.

    Les données publiques de marché Binance
    n'exigent pas cette clé.

    Elle est néanmoins supportée pour préparer
    les futures fonctions d'exécution.
    """

    return os.getenv(
        "BINANCE_API_KEY",
        "",
    ).strip()


def _get_binance_api_secret() -> str:
    """
    Récupère éventuellement le secret Binance.

    Utilisé plus tard pour les opérations privées.
    """

    return os.getenv(
        "BINANCE_API_SECRET",
        "",
    ).strip()


# ============================================================
# TIMEFRAME
# ============================================================

def _normalize_timeframe(
    timeframe: str,
) -> str:
    """
    Normalise un timeframe.

    Exemples :

        h4  -> H4
        H1  -> H1
        m15 -> M15
        m5  -> M5
    """

    if not isinstance(
        timeframe,
        str,
    ):
        raise ValueError(
            "Le timeframe doit être "
            "une chaîne de caractères."
        )

    normalized = timeframe.strip().upper()

    if normalized not in VALID_TIMEFRAMES:

        raise ValueError(
            f"Timeframe invalide : {timeframe}. "
            f"Valeurs autorisées : "
            f"{sorted(VALID_TIMEFRAMES)}"
        )

    return normalized


# ============================================================
# TYPE DE MARCHÉ
# ============================================================

def _is_crypto_symbol(
    symbol: str,
) -> bool:
    """
    Détermine si le symbole appartient
    à l'univers crypto de NOVA.
    """

    normalized = (
        symbol.strip().upper()
    )

    return normalized in CRYPTO_SYMBOLS


# ============================================================
# TIMESTAMP TWELVE DATA
# ============================================================

def _parse_timestamp(
    value: str,
) -> datetime:
    """
    Convertit un timestamp Twelve Data
    en datetime UTC.
    """

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"Timestamp invalide : {value}"
        )

    value = value.strip()

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )

    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt,
            )

            return dt.replace(
                tzinfo=timezone.utc
            )

        except ValueError:
            continue

    raise ValueError(
        f"Format de timestamp inconnu : "
        f"{value}"
    )


# ============================================================
# TIMESTAMP BINANCE
# ============================================================

def _parse_binance_timestamp(
    value: int,
) -> datetime:
    """
    Binance retourne les timestamps
    en millisecondes Unix.
    """

    return datetime.fromtimestamp(
        float(value) / 1000.0,
        tz=timezone.utc,
    )


# ============================================================
# CACHE KEY
# ============================================================

def _cache_key(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> Tuple[str, str, int]:

    return (
        symbol.strip().upper(),
        timeframe.strip().upper(),
        int(outputsize),
    )


# ============================================================
# CACHE READ
# ============================================================

def _get_cached_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
    allow_stale: bool = False,
) -> Optional[List[Candle]]:
    """
    Retourne les candles du cache.

    allow_stale=True autorise un cache expiré
    dans le cadre d'un fallback exceptionnel.
    """

    key = _cache_key(
        symbol,
        timeframe,
        outputsize,
    )

    now = time.time()

    with _CACHE_LOCK:

        cached = _CANDLE_CACHE.get(key)

        if cached is None:
            return None

        timestamp = float(
            cached.get(
                "timestamp",
                0.0,
            )
        )

        candles = cached.get(
            "candles"
        )

        if not isinstance(
            candles,
            list,
        ):
            return None

        age = max(
            0.0,
            now - timestamp,
        )

        ttl = CACHE_TTL_SECONDS.get(
            timeframe,
            60,
        )

        # ----------------------------------------------------
        # CACHE FRAIS
        # ----------------------------------------------------

        if age <= ttl:

            with _STATS_LOCK:
                _STATS[
                    "cache_hits"
                ] += 1

            return list(candles)

        # ----------------------------------------------------
        # CACHE STALE
        # ----------------------------------------------------

        if allow_stale:

            stale_limit = (
                STALE_CACHE_MAX_AGE_SECONDS.get(
                    timeframe,
                    300,
                )
            )

            if age <= stale_limit:

                with _STATS_LOCK:
                    _STATS[
                        "stale_cache_hits"
                    ] += 1

                return list(candles)

    return None


# ============================================================
# CACHE WRITE
# ============================================================

def _set_cached_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
    candles: List[Candle],
) -> None:

    key = _cache_key(
        symbol,
        timeframe,
        outputsize,
    )

    with _CACHE_LOCK:

        _CANDLE_CACHE[key] = {
            "candles": list(candles),
            "timestamp": time.time(),
        }


# ============================================================
# CLEAR CACHE
# ============================================================

def clear_cache() -> None:
    """
    Vide complètement le cache marché.
    """

    with _CACHE_LOCK:
        _CANDLE_CACHE.clear()


def clear_symbol_cache(
    symbol: str,
) -> None:
    """
    Supprime tout le cache d'un symbole.
    """

    normalized = (
        symbol.strip().upper()
    )

    with _CACHE_LOCK:

        keys_to_delete = [
            key
            for key in _CANDLE_CACHE
            if key[0] == normalized
        ]

        for key in keys_to_delete:
            del _CANDLE_CACHE[key]


# ============================================================
# TWELVE RATE LIMIT
# ============================================================

def _is_twelve_rate_limited() -> bool:

    with _RATE_LIMIT_LOCK:
        return (
            time.time()
            < _RATE_LIMIT_UNTIL
        )


def _remaining_twelve_rate_limit_seconds() -> int:

    with _RATE_LIMIT_LOCK:

        remaining = (
            _RATE_LIMIT_UNTIL
            - time.time()
        )

    return max(
        0,
        int(round(remaining)),
    )


def _activate_twelve_rate_limit(
    seconds: int,
) -> None:

    global _RATE_LIMIT_UNTIL

    with _RATE_LIMIT_LOCK:

        new_until = (
            time.time()
            + max(1, seconds)
        )

        if new_until > _RATE_LIMIT_UNTIL:
            _RATE_LIMIT_UNTIL = new_until


def _clear_twelve_rate_limit() -> None:

    global _RATE_LIMIT_UNTIL

    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_UNTIL = 0.0


# ============================================================
# BINANCE RATE LIMIT
# ============================================================

def _is_binance_rate_limited() -> bool:

    with _BINANCE_RATE_LIMIT_LOCK:
        return (
            time.time()
            < _BINANCE_RATE_LIMIT_UNTIL
        )


def _remaining_binance_rate_limit_seconds() -> int:

    with _BINANCE_RATE_LIMIT_LOCK:

        remaining = (
            _BINANCE_RATE_LIMIT_UNTIL
            - time.time()
        )

    return max(
        0,
        int(round(remaining)),
    )


def _activate_binance_rate_limit(
    seconds: int,
) -> None:

    global _BINANCE_RATE_LIMIT_UNTIL

    with _BINANCE_RATE_LIMIT_LOCK:

        new_until = (
            time.time()
            + max(1, seconds)
        )

        if (
            new_until
            > _BINANCE_RATE_LIMIT_UNTIL
        ):
            _BINANCE_RATE_LIMIT_UNTIL = (
                new_until
            )


def _clear_binance_rate_limit() -> None:

    global _BINANCE_RATE_LIMIT_UNTIL

    with _BINANCE_RATE_LIMIT_LOCK:
        _BINANCE_RATE_LIMIT_UNTIL = 0.0


# ============================================================
# TWELVE API ERROR
# ============================================================

def _parse_api_error(
    response: requests.Response,
) -> str:
    """
    Extrait un message Twelve Data
    sans exposer la clé API.
    """

    try:

        data = response.json()

        if isinstance(
            data,
            dict,
        ):

            message = data.get(
                "message"
            )

            if message:
                return str(message)

            code = data.get(
                "code"
            )

            if code:
                return (
                    f"Code API : {code}"
                )

    except Exception:
        pass

    text = response.text.strip()

    if text:
        return text[:300]

    return (
        f"HTTP {response.status_code}"
    )


# ============================================================
# TWELVE DATA REQUEST
# ============================================================

def _request_twelve_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> List[Candle]:
    """
    Récupère les candles via Twelve Data.
    """

    timeframe = _normalize_timeframe(
        timeframe
    )

    interval = TIMEFRAME_MAP[
        timeframe
    ]

    api_key = (
        _get_twelve_data_api_key()
    )

    params = {
        "symbol": symbol.strip().upper(),
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
    }

    last_error: Optional[
        Exception
    ] = None

    for attempt in range(
        TWELVE_MAX_RETRIES
    ):

        if _is_twelve_rate_limited():

            remaining = (
                _remaining_twelve_rate_limit_seconds()
            )

            raise RuntimeError(
                "Limite Twelve Data active. "
                f"Réessayer dans environ "
                f"{remaining}s."
            )

        try:

            with _STATS_LOCK:
                _STATS[
                    "api_requests"
                ] += 1

                _STATS[
                    "twelve_requests"
                ] += 1

            response = requests.get(
                TWELVE_DATA_URL,
                params=params,
                timeout=TWELVE_REQUEST_TIMEOUT,
            )

            # ------------------------------------------------
            # 429
            # ------------------------------------------------

            if response.status_code == 429:

                with _STATS_LOCK:
                    _STATS[
                        "twelve_rate_limit_hits"
                    ] += 1

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:
                    retry_seconds = int(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    retry_seconds = (
                        TWELVE_RETRY_DELAYS[
                            min(
                                attempt,
                                len(
                                    TWELVE_RETRY_DELAYS
                                ) - 1,
                            )
                        ]
                    )

                retry_seconds = min(
                    max(
                        retry_seconds,
                        5,
                    ),
                    60,
                )

                _activate_twelve_rate_limit(
                    retry_seconds
                )

                last_error = RuntimeError(
                    "Limite Twelve Data atteinte."
                )

                if attempt < (
                    TWELVE_MAX_RETRIES - 1
                ):

                    time.sleep(
                        retry_seconds
                    )

                    continue

                raise last_error

            # ------------------------------------------------
            # HTTP 4xx
            # ------------------------------------------------

            if (
                400
                <= response.status_code
                < 500
            ):

                message = (
                    _parse_api_error(
                        response
                    )
                )

                raise RuntimeError(
                    "Erreur Twelve Data "
                    f"HTTP {response.status_code}: "
                    f"{message}"
                )

            # ------------------------------------------------
            # HTTP 5xx
            # ------------------------------------------------

            if response.status_code >= 500:

                last_error = RuntimeError(
                    "Erreur serveur Twelve Data "
                    f"HTTP {response.status_code}"
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

                    time.sleep(delay)

                    continue

                raise last_error

            # ------------------------------------------------
            # JSON
            # ------------------------------------------------

            try:

                data = response.json()

            except json.JSONDecodeError as exc:

                last_error = RuntimeError(
                    "Réponse Twelve Data "
                    "invalide."
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

                    time.sleep(delay)

                    continue

                raise last_error from exc

            # ------------------------------------------------
            # API ERROR
            # ------------------------------------------------

            if isinstance(
                data,
                dict,
            ):

                status = str(
                    data.get(
                        "status",
                        "",
                    )
                ).lower()

                if status == "error":

                    message = data.get(
                        "message",
                        "Erreur inconnue.",
                    )

                    raise RuntimeError(
                        "Twelve Data : "
                        f"{message}"
                    )

            values = data.get(
                "values"
            )

            if not isinstance(
                values,
                list,
            ):

                raise RuntimeError(
                    "Twelve Data n'a retourné "
                    "aucune donnée candle."
                )

            # ------------------------------------------------
            # PARSING
            # ------------------------------------------------

            candles: List[
                Candle
            ] = []

            for item in values:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                try:

                    timestamp = (
                        _parse_timestamp(
                            item["datetime"]
                        )
                    )

                    candle = Candle(
                        timestamp=timestamp,
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
                        ),
                    )

                    candles.append(
                        candle
                    )

                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    continue

            if not candles:

                raise RuntimeError(
                    "Aucune candle exploitable "
                    "dans la réponse Twelve Data."
                )

            candles.sort(
                key=lambda candle:
                candle.timestamp
            )

            _clear_twelve_rate_limit()

            with _STATS_LOCK:

                _STATS[
                    "successful_requests"
                ] += 1

                _STATS[
                    "twelve_successful_requests"
                ] += 1

            return candles

        except requests.RequestException as exc:

            last_error = RuntimeError(
                "Erreur réseau Twelve Data : "
                f"{exc}"
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

                time.sleep(delay)

                continue

            raise last_error from exc

        except RuntimeError:
            raise

        except Exception as exc:

            last_error = RuntimeError(
                f"Erreur données Twelve Data : "
                f"{exc}"
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

                time.sleep(delay)

                continue

            raise last_error from exc

    if last_error:
        raise last_error

    raise RuntimeError(
        "Impossible de récupérer les "
        "données Twelve Data."
    )


# ============================================================
# BINANCE REQUEST
# ============================================================

def _request_binance_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> List[Candle]:
    """
    Récupère les candles publiques Binance.

    Les endpoints publics de marché ne nécessitent
    pas de clé API.
    """

    timeframe = _normalize_timeframe(
        timeframe
    )

    binance_symbol = (
        BINANCE_SYMBOL_MAP.get(
            symbol.strip().upper()
        )
    )

    if not binance_symbol:

        raise RuntimeError(
            f"Symbole crypto non supporté "
            f"par Binance : {symbol}"
        )

    interval = (
        BINANCE_INTERVAL_MAP[
            timeframe
        ]
    )

    # Binance limite le nombre de candles
    # par requête. On protège la valeur.
    limit = min(
        max(
            int(outputsize),
            1,
        ),
        1000,
    )

    params = {
        "symbol": binance_symbol,
        "interval": interval,
        "limit": limit,
    }

    last_error: Optional[
        Exception
    ] = None

    for attempt in range(
        BINANCE_MAX_RETRIES
    ):

        if _is_binance_rate_limited():

            remaining = (
                _remaining_binance_rate_limit_seconds()
            )

            raise RuntimeError(
                "Limite Binance active. "
                f"Réessayer dans environ "
                f"{remaining}s."
            )

        try:

            with _STATS_LOCK:

                _STATS[
                    "api_requests"
                ] += 1

                _STATS[
                    "binance_requests"
                ] += 1

            response = requests.get(
                BINANCE_KLINES_URL,
                params=params,
                timeout=BINANCE_REQUEST_TIMEOUT,
            )

            # ------------------------------------------------
            # RATE LIMIT
            # ------------------------------------------------

            if response.status_code in (
                418,
                429,
            ):

                with _STATS_LOCK:
                    _STATS[
                        "binance_rate_limit_hits"
                    ] += 1

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:
                    retry_seconds = int(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    retry_seconds = (
                        BINANCE_RETRY_DELAYS[
                            min(
                                attempt,
                                len(
                                    BINANCE_RETRY_DELAYS
                                ) - 1,
                            )
                        ]
                    )

                retry_seconds = min(
                    max(
                        retry_seconds,
                        2,
                    ),
                    60,
                )

                _activate_binance_rate_limit(
                    retry_seconds
                )

                last_error = RuntimeError(
                    "Limite Binance atteinte."
                )

                if attempt < (
                    BINANCE_MAX_RETRIES - 1
                ):

                    time.sleep(
                        retry_seconds
                    )

                    continue

                raise last_error

            # ------------------------------------------------
            # HTTP ERROR
            # ------------------------------------------------

            if (
                response.status_code
                >= 400
            ):

                try:
                    error_data = (
                        response.json()
                    )

                    message = error_data.get(
                        "msg",
                        response.text[:300],
                    )

                except Exception:
                    message = response.text[
                        :300
                    ]

                raise RuntimeError(
                    "Erreur Binance "
                    f"HTTP {response.status_code}: "
                    f"{message}"
                )

            # ------------------------------------------------
            # JSON
            # ------------------------------------------------

            try:

                data = response.json()

            except json.JSONDecodeError as exc:

                last_error = RuntimeError(
                    "Réponse Binance "
                    "invalide."
                )

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

                    time.sleep(delay)

                    continue

                raise last_error from exc

            if not isinstance(
                data,
                list,
            ):

                raise RuntimeError(
                    "Binance n'a retourné "
                    "aucune donnée candle."
                )

            # ------------------------------------------------
            # PARSING
            # ------------------------------------------------

            candles: List[
                Candle
            ] = []

            for item in data:

                if not isinstance(
                    item,
                    list,
                ):
                    continue

                if len(item) < 6:
                    continue

                try:

                    timestamp = (
                        _parse_binance_timestamp(
                            int(item[0])
                        )
                    )

                    candle = Candle(
                        timestamp=timestamp,
                        open=float(item[1]),
                        high=float(item[2]),
                        low=float(item[3]),
                        close=float(item[4]),
                        volume=float(item[5]),
                    )

                    candles.append(
                        candle
                    )

                except (
                    TypeError,
                    ValueError,
                    IndexError,
                ):
                    continue

            if not candles:

                raise RuntimeError(
                    "Aucune candle exploitable "
                    "dans la réponse Binance."
                )

            candles.sort(
                key=lambda candle:
                candle.timestamp
            )

            _clear_binance_rate_limit()

            with _STATS_LOCK:

                _STATS[
                    "successful_requests"
                ] += 1

                _STATS[
                    "binance_successful_requests"
                ] += 1

            return candles

        except requests.RequestException as exc:

            last_error = RuntimeError(
                "Erreur réseau Binance : "
                f"{exc}"
            )

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

                time.sleep(delay)

                continue

            raise last_error from exc

        except RuntimeError:
            raise

        except Exception as exc:

            last_error = RuntimeError(
                f"Erreur données Binance : "
                f"{exc}"
            )

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

                time.sleep(delay)

                continue

            raise last_error from exc

    if last_error:
        raise last_error

    raise RuntimeError(
        "Impossible de récupérer les "
        "données Binance."
    )


# ============================================================
# ROUTEUR MARKET DATA
# ============================================================

def _request_market_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> List[Candle]:
    """
    Route automatiquement la requête.

    Crypto :
        Binance
        ↓
        Twelve Data fallback

    Forex/XAU :
        Twelve Data
    """

    normalized_symbol = (
        symbol.strip().upper()
    )

    # ========================================================
    # CRYPTO -> BINANCE
    # ========================================================

    if _is_crypto_symbol(
        normalized_symbol
    ):

        try:

            return _request_binance_candles(
                symbol=normalized_symbol,
                timeframe=timeframe,
                outputsize=outputsize,
            )

        except Exception:

            # Binance indisponible :
            # Twelve Data devient le secours.

            with _STATS_LOCK:
                _STATS[
                    "fallback_to_twelve"
                ] += 1

            return _request_twelve_candles(
                symbol=normalized_symbol,
                timeframe=timeframe,
                outputsize=outputsize,
            )

    # ========================================================
    # FOREX / XAU -> TWELVE DATA
    # ========================================================

    return _request_twelve_candles(
        symbol=normalized_symbol,
        timeframe=timeframe,
        outputsize=outputsize,
    )


# ============================================================
# GET CANDLES
# ============================================================

def get_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> List[Candle]:
    """
    Fonction principale utilisée par NOVA.

    Ordre :

        1. Cache frais
        2. Source adaptée
        3. Fallback
        4. Cache stale exceptionnel
    """

    if not symbol or not isinstance(
        symbol,
        str,
    ):

        raise ValueError(
            "Symbole invalide."
        )

    timeframe = _normalize_timeframe(
        timeframe
    )

    if outputsize <= 0:

        raise ValueError(
            "outputsize doit être "
            "supérieur à 0."
        )

    # ========================================================
    # CACHE FRAIS
    # ========================================================

    cached = _get_cached_candles(
        symbol,
        timeframe,
        outputsize,
        allow_stale=False,
    )

    if cached is not None:
        return cached

    # ========================================================
    # API
    # ========================================================

    try:

        candles = (
            _request_market_candles(
                symbol=symbol,
                timeframe=timeframe,
                outputsize=outputsize,
            )
        )

        _set_cached_candles(
            symbol,
            timeframe,
            outputsize,
            candles,
        )

        return candles

    except Exception as primary_error:

        with _STATS_LOCK:
            _STATS[
                "errors"
            ] += 1

        # ====================================================
        # CACHE STALE
        # ====================================================

        stale = _get_cached_candles(
            symbol,
            timeframe,
            outputsize,
            allow_stale=True,
        )

        if stale is not None:
            return stale

        raise primary_error


# ============================================================
# DERNIER PRIX
# ============================================================

def get_latest_price(
    symbol: str,
) -> float:
    """
    Retourne le dernier prix disponible.

    Le prix utilisé par NOVA provient du M5.
    """

    candles = get_candles(
        symbol=symbol,
        timeframe="M5",
        outputsize=2,
    )

    if not candles:

        raise RuntimeError(
            f"Aucun prix disponible "
            f"pour {symbol}."
        )

    return float(
        candles[-1].close
    )


# ============================================================
# ALIAS COMPATIBILITÉ
# ============================================================

def get_price(
    symbol: str,
) -> float:
    """
    Alias conservé pour les anciens modules.
    """

    return get_latest_price(
        symbol
    )


# ============================================================
# STATISTIQUES
# ============================================================

def get_market_data_stats(
) -> Dict[str, int]:
    """
    Retourne les statistiques du moteur
    de données.
    """

    with _STATS_LOCK:

        return dict(_STATS)


# ============================================================
# RESET STATISTIQUES
# ============================================================

def reset_market_data_stats() -> None:
    """
    Réinitialise les statistiques.
    """

    with _STATS_LOCK:

        for key in _STATS:
            _STATS[key] = 0