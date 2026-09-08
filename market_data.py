"""
NOVA TRADE AI
market_data.py

MOTEUR CENTRAL DES DONNÉES DE MARCHÉ

Timeframes utilisés par la stratégie :
    H4  → tendance globale
    H1  → structure / zones
    M15 → zones / price action
    M5  → confirmation secondaire

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
# CONFIGURATION TWELVE DATA
# ============================================================

BASE_URL = "https://api.twelvedata.com/time_series"

TIMEFRAME_MAP = {
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}

VALID_TIMEFRAMES = set(TIMEFRAME_MAP.keys())

REQUEST_TIMEOUT = 15

MAX_RETRIES = 3

RETRY_DELAYS = (5, 15, 30)


# ============================================================
# CACHE
# ============================================================

# Cache plus long sur les grandes unités de temps.
CACHE_TTL_SECONDS = {
    "H4": 600,    # 10 minutes
    "H1": 300,    # 5 minutes
    "M15": 120,   # 2 minutes
    "M5": 60,     # 1 minute
}

# Durée maximale pendant laquelle une ancienne donnée
# peut être utilisée temporairement en cas de rate limit.
STALE_CACHE_MAX_AGE_SECONDS = {
    "H4": 3600,   # 1 heure
    "H1": 1800,   # 30 minutes
    "M15": 900,   # 15 minutes
    "M5": 300,    # 5 minutes
}


_CACHE_LOCK = Lock()

# key:
# (SYMBOL, TIMEFRAME, OUTPUTSIZE)
#
# value:
# {
#     "candles": [...],
#     "timestamp": float
# }
_CANDLE_CACHE: Dict[
    Tuple[str, str, int],
    Dict[str, object],
] = {}


# ============================================================
# RATE LIMIT GLOBAL
# ============================================================

_RATE_LIMIT_LOCK = Lock()

# Timestamp jusqu'auquel les nouvelles requêtes API
# sont temporairement bloquées.
_RATE_LIMIT_UNTIL = 0.0


# ============================================================
# STATISTIQUES
# ============================================================

_STATS_LOCK = Lock()

_STATS = {
    "api_requests": 0,
    "cache_hits": 0,
    "stale_cache_hits": 0,
    "rate_limit_hits": 0,
    "errors": 0,
    "successful_requests": 0,
}


# ============================================================
# API KEY
# ============================================================

def _get_api_key() -> str:
    """
    Récupère la clé Twelve Data depuis l'environnement.
    """

    key = os.getenv("TWELVE_DATA_API_KEY", "").strip()

    if not key:
        raise RuntimeError(
            "Variable d'environnement TWELVE_DATA_API_KEY absente."
        )

    return key


# ============================================================
# TIMEFRAME
# ============================================================

def _normalize_timeframe(timeframe: str) -> str:
    """
    Normalise un timeframe.

    Exemples :
        h4  -> H4
        H1  -> H1
        m15 -> M15
        m5  -> M5
    """

    if not isinstance(timeframe, str):
        raise ValueError(
            "Le timeframe doit être une chaîne de caractères."
        )

    normalized = timeframe.strip().upper()

    if normalized not in VALID_TIMEFRAMES:
        raise ValueError(
            f"Timeframe invalide : {timeframe}. "
            f"Valeurs autorisées : {sorted(VALID_TIMEFRAMES)}"
        )

    return normalized


# ============================================================
# TIMESTAMP
# ============================================================

def _parse_timestamp(value: str) -> datetime:
    """
    Convertit un timestamp Twelve Data en datetime UTC.
    """

    if not isinstance(value, str):
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
            dt = datetime.strptime(value, fmt)

            return dt.replace(
                tzinfo=timezone.utc
            )

        except ValueError:
            continue

    raise ValueError(
        f"Format de timestamp inconnu : {value}"
    )


# ============================================================
# CACHE
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


def _get_cached_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
    allow_stale: bool = False,
) -> Optional[List[Candle]]:
    """
    Retourne les données du cache si elles sont encore valides.

    Si allow_stale=True, une donnée plus ancienne peut être
    retournée en cas de problème API.
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
            cached.get("timestamp", 0.0)
        )

        candles = cached.get("candles")

        if not isinstance(candles, list):
            return None

        age = now - timestamp

        ttl = CACHE_TTL_SECONDS.get(
            timeframe,
            60,
        )

        if age <= ttl:

            with _STATS_LOCK:
                _STATS["cache_hits"] += 1

            return list(candles)

        if allow_stale:

            stale_limit = STALE_CACHE_MAX_AGE_SECONDS.get(
                timeframe,
                300,
            )

            if age <= stale_limit:

                with _STATS_LOCK:
                    _STATS["stale_cache_hits"] += 1

                return list(candles)

    return None


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


def clear_cache() -> None:
    """
    Vide complètement le cache marché.
    """

    with _CACHE_LOCK:
        _CANDLE_CACHE.clear()


def clear_symbol_cache(symbol: str) -> None:
    """
    Supprime le cache d'un symbole.
    """

    symbol = symbol.strip().upper()

    with _CACHE_LOCK:

        keys_to_delete = [
            key
            for key in _CANDLE_CACHE
            if key[0] == symbol
        ]

        for key in keys_to_delete:
            del _CANDLE_CACHE[key]


# ============================================================
# RATE LIMIT
# ============================================================

def _is_rate_limited() -> bool:

    with _RATE_LIMIT_LOCK:
        return time.time() < _RATE_LIMIT_UNTIL


def _remaining_rate_limit_seconds() -> int:

    with _RATE_LIMIT_LOCK:

        remaining = _RATE_LIMIT_UNTIL - time.time()

    return max(
        0,
        int(round(remaining)),
    )


def _activate_rate_limit(
    seconds: int,
) -> None:

    global _RATE_LIMIT_UNTIL

    with _RATE_LIMIT_LOCK:

        new_until = time.time() + max(
            1,
            seconds,
        )

        if new_until > _RATE_LIMIT_UNTIL:
            _RATE_LIMIT_UNTIL = new_until


def _clear_rate_limit() -> None:

    global _RATE_LIMIT_UNTIL

    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_UNTIL = 0.0


# ============================================================
# API ERROR
# ============================================================

def _parse_api_error(
    response: requests.Response,
) -> str:
    """
    Extrait un message d'erreur propre sans exposer
    la clé API.
    """

    try:

        data = response.json()

        if isinstance(data, dict):

            message = data.get("message")

            if message:
                return str(message)

            code = data.get("code")

            if code:
                return f"Code API : {code}"

    except Exception:
        pass

    text = response.text.strip()

    if text:
        return text[:300]

    return f"HTTP {response.status_code}"


# ============================================================
# REQUEST TWELVE DATA
# ============================================================

def _request_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> List[Candle]:

    timeframe = _normalize_timeframe(
        timeframe
    )

    interval = TIMEFRAME_MAP[timeframe]

    api_key = _get_api_key()

    params = {
        "symbol": symbol.strip().upper(),
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
    }

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):

        # ----------------------------------------------------
        # RATE LIMIT GLOBAL
        # ----------------------------------------------------

        if _is_rate_limited():

            remaining = _remaining_rate_limit_seconds()

            raise RuntimeError(
                "Limite Twelve Data active. "
                f"Réessayer dans environ {remaining}s."
            )

        try:

            with _STATS_LOCK:
                _STATS["api_requests"] += 1

            response = requests.get(
                BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            # ------------------------------------------------
            # HTTP 429
            # ------------------------------------------------

            if response.status_code == 429:

                with _STATS_LOCK:
                    _STATS["rate_limit_hits"] += 1

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    retry_seconds = int(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    retry_seconds = RETRY_DELAYS[
                        min(
                            attempt,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]

                retry_seconds = min(
                    max(retry_seconds, 5),
                    60,
                )

                _activate_rate_limit(
                    retry_seconds
                )

                last_error = RuntimeError(
                    "Limite Twelve Data atteinte."
                )

                if attempt < MAX_RETRIES - 1:

                    time.sleep(
                        retry_seconds
                    )

                    continue

                raise last_error

            # ------------------------------------------------
            # AUTRES ERREURS HTTP
            # ------------------------------------------------

            if 400 <= response.status_code < 500:

                message = _parse_api_error(
                    response
                )

                raise RuntimeError(
                    f"Erreur Twelve Data "
                    f"HTTP {response.status_code}: "
                    f"{message}"
                )

            if response.status_code >= 500:

                last_error = RuntimeError(
                    f"Erreur serveur Twelve Data "
                    f"HTTP {response.status_code}"
                )

                if attempt < MAX_RETRIES - 1:

                    delay = RETRY_DELAYS[
                        min(
                            attempt,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]

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

                if attempt < MAX_RETRIES - 1:

                    delay = RETRY_DELAYS[
                        min(
                            attempt,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]

                    time.sleep(delay)

                    continue

                raise last_error from exc

            # ------------------------------------------------
            # ERREUR API
            # ------------------------------------------------

            if isinstance(data, dict):

                status = str(
                    data.get("status", "")
                ).lower()

                if status == "error":

                    message = data.get(
                        "message",
                        "Erreur inconnue.",
                    )

                    raise RuntimeError(
                        f"Twelve Data : {message}"
                    )

            values = data.get("values")

            if not isinstance(values, list):

                raise RuntimeError(
                    "Twelve Data n'a retourné "
                    "aucune donnée candle."
                )

            # ------------------------------------------------
            # PARSING CANDLES
            # ------------------------------------------------

            candles: List[Candle] = []

            for item in values:

                if not isinstance(item, dict):
                    continue

                try:

                    timestamp = _parse_timestamp(
                        item["datetime"]
                    )

                    candle = Candle(
                        timestamp=timestamp,
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=float(
                            item.get(
                                "volume",
                                0.0,
                            )
                        ),
                    )

                    candles.append(candle)

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

            # Twelve Data peut retourner les candles
            # de la plus récente à la plus ancienne.
            candles.sort(
                key=lambda candle: candle.timestamp
            )

            _clear_rate_limit()

            with _STATS_LOCK:
                _STATS["successful_requests"] += 1

            return candles

        except requests.RequestException as exc:

            last_error = RuntimeError(
                f"Erreur réseau Twelve Data : {exc}"
            )

            if attempt < MAX_RETRIES - 1:

                delay = RETRY_DELAYS[
                    min(
                        attempt,
                        len(RETRY_DELAYS) - 1,
                    )
                ]

                time.sleep(delay)

                continue

            raise last_error from exc

        except RuntimeError:
            raise

        except Exception as exc:

            last_error = RuntimeError(
                f"Erreur données marché : {exc}"
            )

            if attempt < MAX_RETRIES - 1:

                delay = RETRY_DELAYS[
                    min(
                        attempt,
                        len(RETRY_DELAYS) - 1,
                    )
                ]

                time.sleep(delay)

                continue

            raise last_error from exc

    if last_error:

        raise last_error

    raise RuntimeError(
        "Impossible de récupérer les données marché."
    )


# ============================================================
# GET CANDLES
# ============================================================

def get_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> List[Candle]:

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
            "outputsize doit être supérieur à 0."
        )

    # --------------------------------------------------------
    # CACHE FRAIS
    # --------------------------------------------------------

    cached = _get_cached_candles(
        symbol,
        timeframe,
        outputsize,
        allow_stale=False,
    )

    if cached is not None:
        return cached

    # --------------------------------------------------------
    # RATE LIMIT
    # --------------------------------------------------------

    if _is_rate_limited():

        stale = _get_cached_candles(
            symbol,
            timeframe,
            outputsize,
            allow_stale=True,
        )

        if stale is not None:
            return stale

        remaining = _remaining_rate_limit_seconds()

        raise RuntimeError(
            "Limite Twelve Data active et "
            f"aucune donnée récente en cache "
            f"pour {symbol} {timeframe}. "
            f"Réessayer dans environ {remaining}s."
        )

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------

    try:

        candles = _request_candles(
            symbol=symbol,
            timeframe=timeframe,
            outputsize=outputsize,
        )

        _set_cached_candles(
            symbol,
            timeframe,
            outputsize,
            candles,
        )

        return candles

    except Exception:

        with _STATS_LOCK:
            _STATS["errors"] += 1

        # ----------------------------------------------------
        # FALLBACK CACHE STALE
        # ----------------------------------------------------

        stale = _get_cached_candles(
            symbol,
            timeframe,
            outputsize,
            allow_stale=True,
        )

        if stale is not None:
            return stale

        raise


# ============================================================
# DERNIÈRE DONNÉE
# ============================================================

def get_latest_price(
    symbol: str,
) -> float:

    candles = get_candles(
        symbol=symbol,
        timeframe="M5",
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
# ALIAS COMPATIBILITÉ
# ============================================================

def get_price(
    symbol: str,
) -> float:
    """
    Alias conservé pour compatibilité
    avec les anciens modules.
    """

    return get_latest_price(
        symbol
    )


# ============================================================
# STATISTIQUES
# ============================================================

def get_market_data_stats() -> Dict[str, int]:

    with _STATS_LOCK:

        return dict(_STATS)


# ============================================================
# RESET STATISTIQUES
# ============================================================

def reset_market_data_stats() -> None:

    with _STATS_LOCK:

        for key in _STATS:
            _STATS[key] = 0