"""
NOVA TRADE AI
market_data.py

Gestion robuste des données Twelve Data.

Objectifs :
- Réduire fortement les appels API inutiles
- Protéger contre HTTP 429
- Cache adapté à chaque timeframe
- Cooldown global après rate limit
- Ne jamais exposer la clé API dans les erreurs
- Conserver les mêmes fonctions publiques :
    get_candles()
    get_latest_price()
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional, Tuple

import requests


BASE_URL = "https://api.twelvedata.com/time_series"

TIMEFRAME_MAP = {
    "D1": "1day",
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}

REQUEST_TIMEOUT = 15

# ---------------------------------------------------------------------
# CACHE
# ---------------------------------------------------------------------

# Cache plus long pour les grands timeframes.
# Cela évite de redemander H4/H1 à Twelve Data à chaque analyse.
CACHE_TTL_SECONDS = {
    "D1": 1800,     # 30 min
    "H4": 900,      # 15 min
    "H1": 300,      # 5 min
    "M15": 90,      # 1 min 30
    "M5": 30,       # 30 sec
}

# Durée maximale pendant laquelle une donnée ancienne peut être
# utilisée en cas de rate limit.
STALE_CACHE_MAX_AGE_SECONDS = {
    "D1": 3600,
    "H4": 1800,
    "H1": 900,
    "M15": 300,
    "M5": 120,
}

_CACHE_LOCK = Lock()

_CANDLE_CACHE: Dict[
    Tuple[str, str, int],
    Tuple[float, List["Candle"]]
] = {}

# Cooldown global Twelve Data après un HTTP 429.
_RATE_LIMIT_UNTIL = 0.0

# Petite protection contre plusieurs requêtes concurrentes.
_REQUEST_LOCK = Lock()


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# ---------------------------------------------------------------------
# API KEY
# ---------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.getenv("TWELVE_DATA_API_KEY", "").strip()

    if not key:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY non configurée."
        )

    return key


# ---------------------------------------------------------------------
# TIMESTAMP
# ---------------------------------------------------------------------

def _parse_timestamp(value: str) -> datetime:
    value = str(value).strip()

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(
        f"Timestamp Twelve Data invalide : {value}"
    )


# ---------------------------------------------------------------------
# CACHE
# ---------------------------------------------------------------------

def _cache_key(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> Tuple[str, str, int]:
    return (
        symbol.upper().strip(),
        timeframe.upper().strip(),
        int(outputsize),
    )


def _get_cached(
    symbol: str,
    timeframe: str,
    outputsize: int,
    allow_stale: bool = False,
) -> Optional[List[Candle]]:

    key = _cache_key(symbol, timeframe, outputsize)
    now = time.monotonic()

    with _CACHE_LOCK:
        item = _CANDLE_CACHE.get(key)

    if item is None:
        return None

    saved_at, candles = item
    age = now - saved_at

    timeframe = timeframe.upper()

    fresh_ttl = CACHE_TTL_SECONDS.get(
        timeframe,
        60,
    )

    if age <= fresh_ttl:
        return list(candles)

    if allow_stale:
        stale_limit = STALE_CACHE_MAX_AGE_SECONDS.get(
            timeframe,
            300,
        )

        if age <= stale_limit:
            return list(candles)

    return None


def _save_cache(
    symbol: str,
    timeframe: str,
    outputsize: int,
    candles: List[Candle],
) -> None:

    key = _cache_key(symbol, timeframe, outputsize)

    with _CACHE_LOCK:
        _CANDLE_CACHE[key] = (
            time.monotonic(),
            list(candles),
        )


# ---------------------------------------------------------------------
# RATE LIMIT
# ---------------------------------------------------------------------

def _rate_limit_active() -> bool:
    with _CACHE_LOCK:
        return time.monotonic() < _RATE_LIMIT_UNTIL


def _set_rate_limit_cooldown(seconds: float) -> None:
    global _RATE_LIMIT_UNTIL

    seconds = max(1.0, min(float(seconds), 300.0))

    with _CACHE_LOCK:
        _RATE_LIMIT_UNTIL = max(
            _RATE_LIMIT_UNTIL,
            time.monotonic() + seconds,
        )


def _remaining_rate_limit() -> int:
    with _CACHE_LOCK:
        remaining = _RATE_LIMIT_UNTIL - time.monotonic()

    return max(0, int(remaining))


# ---------------------------------------------------------------------
# ERROR PARSING
# ---------------------------------------------------------------------

def _parse_api_error(response: requests.Response) -> str:
    try:
        data = response.json()
    except Exception:
        data = None

    if isinstance(data, dict):
        message = data.get("message")

        if message:
            return str(message)

        code = data.get("code")

        if code:
            return f"Erreur Twelve Data code {code}"

    return (
        f"Erreur Twelve Data HTTP {response.status_code}"
    )


# ---------------------------------------------------------------------
# REQUEST
# ---------------------------------------------------------------------

def _request_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> List[Candle]:

    global _RATE_LIMIT_UNTIL

    api_key = _get_api_key()

    timeframe = timeframe.upper()

    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(
            f"Timeframe invalide : {timeframe}. "
            f"Valeurs autorisées : {list(TIMEFRAME_MAP)}"
        )

    interval = TIMEFRAME_MAP[timeframe]

    # Si Twelve Data vient de nous limiter, inutile de refaire
    # immédiatement une requête.
    if _rate_limit_active():
        remaining = _remaining_rate_limit()

        raise RuntimeError(
            "Limite Twelve Data temporairement active "
            f"(cooldown encore actif : {remaining}s)."
        )

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
    }

    with _REQUEST_LOCK:

        # Double vérification après attente du lock.
        if _rate_limit_active():
            remaining = _remaining_rate_limit()

            raise RuntimeError(
                "Limite Twelve Data temporairement active "
                f"(cooldown encore actif : {remaining}s)."
            )

        try:
            response = requests.get(
                BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

        except requests.RequestException as exc:
            raise RuntimeError(
                f"Erreur réseau Twelve Data : {exc}"
            ) from exc

        # -------------------------------------------------------------
        # HTTP 429
        # -------------------------------------------------------------

        if response.status_code == 429:

            retry_after = response.headers.get(
                "Retry-After"
            )

            try:
                retry_seconds = float(retry_after)
            except (
                TypeError,
                ValueError,
            ):
                retry_seconds = 60.0

            # Minimum 60 secondes pour éviter de marteler
            # Twelve Data.
            retry_seconds = max(
                retry_seconds,
                60.0,
            )

            _set_rate_limit_cooldown(
                retry_seconds
            )

            raise RuntimeError(
                "Limite Twelve Data atteinte "
                f"(HTTP 429). Cooldown activé : "
                f"{int(retry_seconds)}s."
            )

        # -------------------------------------------------------------
        # Autres erreurs HTTP
        # -------------------------------------------------------------

        if response.status_code >= 500:

            raise RuntimeError(
                _parse_api_error(response)
            )

        if response.status_code >= 400:

            raise RuntimeError(
                _parse_api_error(response)
            )

        # -------------------------------------------------------------
        # JSON
        # -------------------------------------------------------------

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Réponse Twelve Data invalide."
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                "Réponse Twelve Data inattendue."
            )

        if data.get("status") == "error":

            message = data.get(
                "message",
                "Erreur inconnue Twelve Data.",
            )

            raise RuntimeError(
                f"Twelve Data : {message}"
            )

        values = data.get("values")

        if not values:
            raise RuntimeError(
                f"Aucune donnée disponible pour "
                f"{symbol} {timeframe}."
            )

        candles: List[Candle] = []

        for item in reversed(values):

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
                        item.get("volume", 0) or 0
                    ),
                )

                candles.append(candle)

            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:

                raise RuntimeError(
                    "Données OHLC Twelve Data invalides."
                ) from exc

        if not candles:
            raise RuntimeError(
                f"Aucune bougie valide pour "
                f"{symbol} {timeframe}."
            )

        return candles


# ---------------------------------------------------------------------
# PUBLIC : GET CANDLES
# ---------------------------------------------------------------------

def get_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 100,
) -> List[Candle]:

    symbol = symbol.upper().strip()
    timeframe = timeframe.upper().strip()

    if not symbol:
        raise ValueError(
            "Symbol vide."
        )

    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(
            f"Timeframe invalide : {timeframe}. "
            f"Valeurs autorisées : {list(TIMEFRAME_MAP)}"
        )

    if outputsize <= 0:
        raise ValueError(
            "outputsize doit être supérieur à 0."
        )

    # -------------------------------------------------------------
    # 1. Cache frais
    # -------------------------------------------------------------

    cached = _get_cached(
        symbol,
        timeframe,
        outputsize,
        allow_stale=False,
    )

    if cached is not None:
        return cached

    # -------------------------------------------------------------
    # 2. Si rate limit actif, utiliser éventuellement le cache
    #    ancien plutôt que de provoquer une nouvelle requête.
    # -------------------------------------------------------------

    if _rate_limit_active():

        stale = _get_cached(
            symbol,
            timeframe,
            outputsize,
            allow_stale=True,
        )

        if stale is not None:
            return stale

        remaining = _remaining_rate_limit()

        raise RuntimeError(
            "Limite Twelve Data active "
            f"et aucune donnée récente en cache "
            f"pour {symbol} {timeframe}. "
            f"Réessayer dans environ {remaining}s."
        )

    # -------------------------------------------------------------
    # 3. Requête API
    # -------------------------------------------------------------

    try:

        candles = _request_candles(
            symbol,
            timeframe,
            outputsize,
        )

        _save_cache(
            symbol,
            timeframe,
            outputsize,
            candles,
        )

        return candles

    except Exception as exc:

        # ---------------------------------------------------------
        # 4. Dernier recours : cache ancien mais encore acceptable
        # ---------------------------------------------------------

        stale = _get_cached(
            symbol,
            timeframe,
            outputsize,
            allow_stale=True,
        )

        if stale is not None:
            return stale

        raise RuntimeError(
            f"Impossible de récupérer les données "
            f"{symbol} {timeframe}: {exc}"
        ) from exc


# ---------------------------------------------------------------------
# PUBLIC : LATEST PRICE
# ---------------------------------------------------------------------

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