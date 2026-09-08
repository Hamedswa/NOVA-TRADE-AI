"""
NOVA TRADE AI
market_data.py
Architecture :
- FOREX + XAU/USD -> Twelve Data UNIQUEMENT
- CRYPTO -> Coinbase Exchange UNIQUEMENT
- Crypto H4 -> agrégation de bougies H1
- Aucun fallback crypto -> Twelve Data
- Cache local avec TTL par timeframe
- Protection renforcée contre les rate limits / quotas Twelve Data
"""
from __future__ import annotations
import os
import sys
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any
import requests
# ============================================================
# CONFIGURATION
# ============================================================
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY", "").strip()
TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"
TWELVE_PRICE_URL = "https://api.twelvedata.com/price"
COINBASE_BASE_URL = "https://api.exchange.coinbase.com"
REQUEST_TIMEOUT = 15
# IMPORTANT :
# On ne répète PAS une requête Twelve Data après un 429.
MAX_RETRIES = 3
RETRY_DELAYS = (2, 4, 8)
# ============================================================
# TIMEFRAMES
# ============================================================
TIMEFRAME_MAP = {
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}
COINBASE_GRANULARITY = {
    "H1": 3600,
    "M15": 900,
    "M5": 300,
}
# ============================================================
# CRYPTO
# ============================================================
CRYPTO_SYMBOL_MAP = {
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "SOL/USD": "SOL-USD",
    "BNB/USD": "BNB-USD",
    "XRP/USD": "XRP-USD",
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
STALE_MAX = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 5 * 60,
}
_cache: dict[
    tuple[str, str],
    tuple[float, list[dict[str, Any]]]
] = {}
_cache_lock = Lock()
# ============================================================
# PROTECTION TWELVE DATA
# ============================================================
_last_twelve_request = 0.0
# Cooldown après HTTP 429
_twelve_rate_locked_until = 0.0
# Blocage long si quota/crédits journaliers épuisés
_twelve_quota_locked_until = 0.0
# Intervalle minimum entre requêtes
TWELVE_MIN_REQUEST_INTERVAL = 3.0
# Après 429 : on attend 60 secondes avant toute nouvelle requête
TWELVE_RATE_LIMIT_LOCK_SECONDS = 60
# Après quota journalier : blocage 24h
TWELVE_DAILY_LIMIT_LOCK_SECONDS = 24 * 60 * 60
_request_lock = Lock()
# ============================================================
# UTILITAIRES
# ============================================================
def _normalize_symbol(symbol: str) -> str:
    return (
        str(symbol or "")
        .strip()
        .upper()
        .replace("-", "/")
    )
def _normalize_timeframe(timeframe: str) -> str:
    tf = str(timeframe or "").strip().upper()
    aliases = {
        "4H": "H4",
        "1H": "H1",
        "15M": "M15",
        "15MIN": "M15",
        "5M": "M5",
        "5MIN": "M5",
    }
    return aliases.get(tf, tf)
def _is_crypto(symbol: str) -> bool:
    return _normalize_symbol(symbol) in CRYPTO_SYMBOL_MAP
def _now() -> float:
    return time.time()
def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
# ============================================================
# CACHE
# ============================================================
def _cache_get(
    symbol: str,
    timeframe: str,
    allow_stale: bool = False,
) -> list[dict[str, Any]] | None:
    key = (
        _normalize_symbol(symbol),
        _normalize_timeframe(timeframe),
    )
    with _cache_lock:
        item = _cache.get(key)
    if item is None:
        return None
    saved_at, candles = item
    age = _now() - saved_at
    tf = key[1]
    if allow_stale:
        max_age = STALE_MAX.get(tf, 300)
    else:
        max_age = CACHE_TTL.get(tf, 0)
    if age > max_age:
        return None
    return list(candles)
def _cache_set(
    symbol: str,
    timeframe: str,
    candles: list[dict[str, Any]],
) -> None:
    key = (
        _normalize_symbol(symbol),
        _normalize_timeframe(timeframe),
    )
    with _cache_lock:
        _cache[key] = (
            _now(),
            list(candles),
        )
def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
# ============================================================
# PROTECTION TWELVE DATA
# ============================================================
def _wait_twelve_rate_limit() -> bool:
    """
    Vérifie les cooldowns Twelve Data.
    Retourne False si Twelve Data est temporairement bloqué.
    """
    global _last_twelve_request
    with _request_lock:
        now = _now()
        # ----------------------------------------------------
        # QUOTA JOURNALIER
        # ----------------------------------------------------
        if now < _twelve_quota_locked_until:
            remaining = int(
                _twelve_quota_locked_until - now
            )
            print(
                "DATA Twelve Data : "
                f"quota bloqué ({remaining}s restantes)."
            )
            return False
        # ----------------------------------------------------
        # RATE LIMIT 429
        # ----------------------------------------------------
        if now < _twelve_rate_locked_until:
            remaining = int(
                _twelve_rate_locked_until - now
            )
            print(
                "DATA Twelve Data : "
                f"rate limit cooldown ({remaining}s)."
            )
            return False
        # ----------------------------------------------------
        # INTERVALLE ENTRE REQUÊTES
        # ----------------------------------------------------
        elapsed = now - _last_twelve_request
        if elapsed < TWELVE_MIN_REQUEST_INTERVAL:
            time.sleep(
                TWELVE_MIN_REQUEST_INTERVAL - elapsed
            )
        _last_twelve_request = _now()
        return True
def _lock_twelve_rate_limit() -> None:
    global _twelve_rate_locked_until
    _twelve_rate_locked_until = (
        _now() +
        TWELVE_RATE_LIMIT_LOCK_SECONDS
    )
def _lock_twelve_quota() -> None:
    global _twelve_quota_locked_until
    _twelve_quota_locked_until = (
        _now() +
        TWELVE_DAILY_LIMIT_LOCK_SECONDS
    )
def _twelve_quota_locked() -> bool:
    return _now() < _twelve_quota_locked_until
def _twelve_rate_locked() -> bool:
    return _now() < _twelve_rate_locked_until
# ============================================================
# TWELVE DATA - PARSING
# ============================================================
def _parse_twelve_candles(
    data: dict[str, Any]
) -> list[dict[str, Any]]:
    values = data.get("values", [])
    if not isinstance(values, list):
        return []
    candles: list[dict[str, Any]] = []
    for row in values:
        if not isinstance(row, dict):
            continue
        dt = row.get("datetime")
        if not dt:
            continue
        candle = {
            "datetime": str(dt),
            "open": _safe_float(row.get("open")),
            "high": _safe_float(row.get("high")),
            "low": _safe_float(row.get("low")),
            "close": _safe_float(row.get("close")),
            "volume": _safe_float(row.get("volume")),
        }
        if candle["high"] <= 0:
            continue
        if candle["low"] <= 0:
            continue
        candles.append(candle)
    candles.sort(
        key=lambda x: x["datetime"]
    )
    return candles
# ============================================================
# TWELVE DATA - CANDLES
# ============================================================
def _request_twelve_candles(
    symbol: str,
    interval: str,
    outputsize: int = 300,
) -> list[dict[str, Any]]:
    if not TWELVE_DATA_KEY:
        print(
            "DATA Twelve Data : "
            "TWELVE_DATA_KEY absente."
        )
        return []
    # --------------------------------------------------------
    # Vérification cooldown
    # --------------------------------------------------------
    if not _wait_twelve_rate_limit():
        return []
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": min(
            max(int(outputsize), 1),
            5000,
        ),
        "apikey": TWELVE_DATA_KEY,
        "timezone": "UTC",
    }
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                TWELVE_DATA_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            # ------------------------------------------------
            # RATE LIMIT
            # ------------------------------------------------
            if response.status_code == 429:
                _lock_twelve_rate_limit()
                print(
                    "DATA Twelve Data : "
                    "HTTP 429 -> cooldown 60s."
                )
                # IMPORTANT :
                # Aucun retry immédiat.
                return []
            # ------------------------------------------------
            # ERREURS SERVEUR
            # ------------------------------------------------
            if response.status_code in (
                500,
                502,
                503,
                504,
            ):
                print(
                    "DATA Twelve Data : "
                    f"HTTP {response.status_code} "
                    f"(tentative {attempt + 1}/"
                    f"{MAX_RETRIES})"
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(
                        RETRY_DELAYS[attempt]
                    )
                    if not _wait_twelve_rate_limit():
                        return []
                    continue
                return []
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return []
            # ------------------------------------------------
            # MESSAGE API
            # ------------------------------------------------
            message = str(
                data.get("message", "")
            )
            message_lower = message.lower()
            # ------------------------------------------------
            # QUOTA / CREDITS
            # ------------------------------------------------
            if (
                "credit" in message_lower
                or "quota" in message_lower
                or "daily" in message_lower
                or "limit" in message_lower
                or "run out" in message_lower
            ):
                print(
                    "DATA Twelve Data QUOTA : "
                    f"{message}"
                )
                _lock_twelve_quota()
                return []
            # ------------------------------------------------
            # ERREUR API
            # ------------------------------------------------
            if data.get("status") == "error":
                print(
                    "DATA Twelve Data erreur : "
                    f"{message or data}"
                )
                return []
            # ------------------------------------------------
            # BOUGIES
            # ------------------------------------------------
            candles = _parse_twelve_candles(
                data
            )
            if not candles:
                print(
                    "DATA Twelve Data : "
                    f"aucune bougie pour "
                    f"{symbol} {interval}"
                )
            return candles
        except requests.RequestException as exc:
            print(
                f"DATA Twelve Data tentative "
                f"{attempt + 1}/{MAX_RETRIES} "
                f"{symbol} {interval} : {exc}"
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(
                    RETRY_DELAYS[attempt]
                )
                if not _wait_twelve_rate_limit():
                    return []
        except ValueError as exc:
            print(
                "DATA Twelve Data JSON invalide "
                f"{symbol} {interval} : {exc}"
            )
            return []
        except Exception as exc:
            print(
                "DATA Twelve Data erreur inattendue "
                f"{symbol} {interval} : {exc}"
            )
            return []
    return []
# ============================================================
# COINBASE - PARSING
# ============================================================
def _parse_coinbase_candles(
    data: Any
) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    candles: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, list):
            continue
        if len(row) < 6:
            continue
        try:
            timestamp = int(row[0])
            low = float(row[1])
            high = float(row[2])
            open_price = float(row[3])
            close = float(row[4])
            volume = float(row[5])
            dt = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            candles.append(
                {
                    "datetime": dt,
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            continue
    candles.sort(
        key=lambda x: x["timestamp"]
    )
    return candles
# ============================================================
# COINBASE - CANDLES
# ============================================================
def _request_coinbase_candles(
    product_id: str,
    granularity: int,
    outputsize: int = 300,
) -> list[dict[str, Any]]:
    url = (
        f"{COINBASE_BASE_URL}/products/"
        f"{product_id}/candles"
    )
    count = min(
        max(int(outputsize), 1),
        300,
    )
    end_ts = int(time.time())
    start_ts = (
        end_ts -
        granularity * (count + 2)
    )
    params = {
        "granularity": granularity,
        "start": datetime.fromtimestamp(
            start_ts,
            tz=timezone.utc,
        ).isoformat(),
        "end": datetime.fromtimestamp(
            end_ts,
            tz=timezone.utc,
        ).isoformat(),
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "NOVA-TRADE-AI/1.0",
    }
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code in (
                429,
                500,
                502,
                503,
                504,
            ):
                print(
                    f"DATA Coinbase HTTP "
                    f"{response.status_code} "
                    f"{product_id} "
                    f"granularity={granularity}"
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(
                        RETRY_DELAYS[attempt]
                    )
                    continue
                return []
            response.raise_for_status()
            candles = _parse_coinbase_candles(
                response.json()
            )
            if not candles:
                print(
                    "DATA Coinbase : "
                    f"aucune bougie pour "
                    f"{product_id} "
                    f"{granularity}"
                )
            return candles[-count:]
        except requests.RequestException as exc:
            print(
                f"DATA Coinbase tentative "
                f"{attempt + 1}/{MAX_RETRIES} "
                f"{product_id} : {exc}"
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(
                    RETRY_DELAYS[attempt]
                )
        except ValueError as exc:
            print(
                "DATA Coinbase JSON invalide "
                f"{product_id} : {exc}"
            )
            return []
        except Exception as exc:
            print(
                "DATA Coinbase erreur inattendue "
                f"{product_id} : {exc}"
            )
            return []
    return []
# ============================================================
# AGRÉGATION H1 -> H4
# ============================================================
def _aggregate_h1_to_h4(
    h1_candles: list[dict[str, Any]],
    outputsize: int = 300,
) -> list[dict[str, Any]]:
    if not h1_candles:
        return []
    buckets: dict[
        int,
        list[dict[str, Any]]
    ] = {}
    for candle in h1_candles:
        timestamp = candle.get(
            "timestamp"
        )
        if timestamp is None:
            try:
                dt = datetime.strptime(
                    candle["datetime"],
                    "%Y-%m-%d %H:%M:%S",
                ).replace(
                    tzinfo=timezone.utc
                )
                timestamp = int(
                    dt.timestamp()
                )
            except Exception:
                continue
        timestamp = int(timestamp)
        h4_seconds = 4 * 3600
        bucket_start = (
            timestamp -
            timestamp % h4_seconds
        )
        buckets.setdefault(
            bucket_start,
            []
        ).append(candle)
    now_ts = int(time.time())
    h4_seconds = 4 * 3600
    current_h4_start = (
        now_ts -
        now_ts % h4_seconds
    )
    result: list[dict[str, Any]] = []
    for bucket_start in sorted(
        buckets.keys()
    ):
        # Ne jamais utiliser la H4 actuellement en formation.
        if bucket_start >= current_h4_start:
            continue
        rows = sorted(
            buckets[bucket_start],
            key=lambda x: x["timestamp"],
        )
        if len(rows) != 4:
            continue
        expected = [
            bucket_start + i * 3600
            for i in range(4)
        ]
        actual = [
            int(row["timestamp"])
            for row in rows
        ]
        if actual != expected:
            continue
        result.append(
            {
                "datetime": datetime.fromtimestamp(
                    bucket_start,
                    tz=timezone.utc,
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "timestamp": bucket_start,
                "open": rows[0]["open"],
                "high": max(
                    row["high"]
                    for row in rows
                ),
                "low": min(
                    row["low"]
                    for row in rows
                ),
                "close": rows[-1]["close"],
                "volume": sum(
                    row["volume"]
                    for row in rows
                ),
            }
        )
    return result[-outputsize:]
def _get_crypto_h4(
    symbol: str,
    outputsize: int = 300,
) -> list[dict[str, Any]]:
    product_id = CRYPTO_SYMBOL_MAP.get(
        _normalize_symbol(symbol)
    )
    if not product_id:
        print(
            "DATA Coinbase : "
            f"symbole crypto inconnu {symbol}"
        )
        return []
    h1_candles = _request_coinbase_candles(
        product_id=product_id,
        granularity=3600,
        outputsize=300,
    )
    return _aggregate_h1_to_h4(
        h1_candles,
        outputsize=outputsize,
    )
# ============================================================
# FOREX / XAU
# ============================================================
def _get_forex_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> list[dict[str, Any]]:
    interval = TIMEFRAME_MAP.get(
        timeframe
    )
    if not interval:
        print(
            "DATA Twelve Data : "
            f"timeframe invalide {timeframe}"
        )
        return []
    return _request_twelve_candles(
        symbol=_normalize_symbol(symbol),
        interval=interval,
        outputsize=outputsize,
    )
# ============================================================
# CRYPTO
# ============================================================
def _get_crypto_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> list[dict[str, Any]]:
    product_id = CRYPTO_SYMBOL_MAP.get(
        _normalize_symbol(symbol)
    )
    if not product_id:
        print(
            "DATA Coinbase : "
            f"symbole non configuré {symbol}"
        )
        return []
    if timeframe == "H4":
        return _get_crypto_h4(
            symbol=symbol,
            outputsize=outputsize,
        )
    granularity = COINBASE_GRANULARITY.get(
        timeframe
    )
    if not granularity:
        print(
            "DATA Coinbase : "
            f"timeframe invalide {timeframe}"
        )
        return []
    return _request_coinbase_candles(
        product_id=product_id,
        granularity=granularity,
        outputsize=outputsize,
    )
# ============================================================
# API PRINCIPALE
# ============================================================
def get_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
    allow_stale: bool = True,
) -> list[dict[str, Any]]:
    symbol = _normalize_symbol(symbol)
    timeframe = _normalize_timeframe(
        timeframe
    )
    if timeframe not in (
        "H4",
        "H1",
        "M15",
        "M5",
    ):
        print(
            "DATA : timeframe invalide "
            f"{timeframe}. "
            "Valeurs autorisées : "
            "H4, H1, M15, M5"
        )
        return []
    # --------------------------------------------------------
    # CACHE FRAIS
    # --------------------------------------------------------
    cached = _cache_get(
        symbol,
        timeframe,
        allow_stale=False,
    )
    if cached:
        return cached[-outputsize:]
    # --------------------------------------------------------
    # PROVIDER
    # --------------------------------------------------------
    if _is_crypto(symbol):
        candles = _get_crypto_candles(
            symbol,
            timeframe,
            outputsize,
        )
        provider = "Coinbase"
    else:
        candles = _get_forex_candles(
            symbol,
            timeframe,
            outputsize,
        )
        provider = "Twelve Data"
    # --------------------------------------------------------
    # DONNÉES OBTENUES
    # --------------------------------------------------------
    if candles:
        _cache_set(
            symbol,
            timeframe,
            candles,
        )
        print(
            f"DATA {symbol} {timeframe} : "
            f"{len(candles)} chandelier "
            f"({provider})"
        )
        return candles[-outputsize:]
    # --------------------------------------------------------
    # CACHE STALE
    # --------------------------------------------------------
    stale = _cache_get(
        symbol,
        timeframe,
        allow_stale=allow_stale,
    )
    if stale:
        print(
            f"DATA {symbol} {timeframe} : "
            f"utilisation cache stale "
            f"({len(stale)} chandelier)"
        )
        return stale[-outputsize:]
    print(
        f"DATA {symbol} {timeframe} : "
        "0 chandelier"
    )
    return []
# ============================================================
# PRIX ACTUEL
# ============================================================
def get_latest_price(
    symbol: str
) -> float | None:
    symbol = _normalize_symbol(
        symbol
    )
    # --------------------------------------------------------
    # CRYPTO -> COINBASE
    # --------------------------------------------------------
    if _is_crypto(symbol):
        product_id = CRYPTO_SYMBOL_MAP.get(
            symbol
        )
        if not product_id:
            return None
        url = (
            f"{COINBASE_BASE_URL}/products/"
            f"{product_id}/ticker"
        )
        try:
            response = requests.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "NOVA-TRADE-AI/1.0"
                    ),
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            price = _safe_float(
                data.get("price")
            )
            if price > 0:
                return price
            return None
        except Exception as exc:
            print(
                f"PRICE Coinbase {symbol} "
                f"erreur : {exc}"
            )
            return None
    # --------------------------------------------------------
    # FOREX/XAU -> TWELVE DATA
    # --------------------------------------------------------
    if not TWELVE_DATA_KEY:
        return None
    if not _wait_twelve_rate_limit():
        return None
    try:
        response = requests.get(
            TWELVE_PRICE_URL,
            params={
                "symbol": symbol,
                "apikey": TWELVE_DATA_KEY,
            },
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 429:
            _lock_twelve_rate_limit()
            print(
                "PRICE Twelve Data : "
                "HTTP 429 -> cooldown 60s."
            )
            return None
        response.raise_for_status()
        data = response.json()
        message = str(
            data.get("message", "")
        )
        message_lower = message.lower()
        if (
            "credit" in message_lower
            or "quota" in message_lower
            or "daily" in message_lower
            or "limit" in message_lower
            or "run out" in message_lower
        ):
            print(
                f"PRICE Twelve Data QUOTA : "
                f"{message}"
            )
            _lock_twelve_quota()
            return None
        price = _safe_float(
            data.get("price")
        )
        if price > 0:
            return price
        return None
    except Exception as exc:
        print(
            f"PRICE Twelve Data "
            f"{symbol} erreur : {exc}"
        )
        return None
# ============================================================
# INFORMATIONS PROVIDER
# ============================================================
def get_provider(
    symbol: str
) -> str:
    if _is_crypto(symbol):
        return "Coinbase"
    return "Twelve Data"
def get_status() -> dict[str, Any]:
    rate_remaining = max(
        0,
        int(
            _twelve_rate_locked_until -
            _now()
        ),
    )
    quota_remaining = max(
        0,
        int(
            _twelve_quota_locked_until -
            _now()
        ),
    )
    return {
        "twelve_data_configured": bool(
            TWELVE_DATA_KEY
        ),
        "twelve_data_rate_limited": (
            _twelve_rate_locked()
        ),
        "twelve_data_rate_cooldown_seconds": (
            rate_remaining
        ),
        "twelve_data_quota_locked": (
            _twelve_quota_locked()
        ),
        "twelve_data_quota_cooldown_seconds": (
            quota_remaining
        ),
        "crypto_provider": (
            "Coinbase Exchange"
        ),
        "crypto_symbols": list(
            CRYPTO_SYMBOL_MAP.keys()
        ),
        "cache_entries": len(_cache),
    }
# ============================================================
# COMPATIBILITÉ
# ============================================================
market_data = sys.modules[__name__]