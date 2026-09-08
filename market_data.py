"""
NOVA TRADE AI
market_data.py
SOURCE DES DONNÉES
------------------
FOREX + XAU/USD -> Twelve Data UNIQUEMENT
CRYPTO          -> Coinbase UNIQUEMENT
Aucun fallback crypto -> Twelve Data.
Protection :
- limitation des requêtes Twelve Data
- cooldown automatique après HTTP 429
- verrou quotidien après quota épuisé
- cache par symbole/timeframe
- pas de retry agressif après 429
- prix crypto via Coinbase
- H4 crypto agrégé depuis H1
"""
from __future__ import annotations
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
# ============================================================
# LOGGING
# ============================================================
logger = logging.getLogger("NOVA_TRADE_AI.MARKET_DATA")
# ============================================================
# ENVIRONNEMENT
# ============================================================
TWELVE_DATA_KEY = (
    os.getenv("TWELVE_DATA_KEY", "").strip()
)
TWELVE_DATA_BASE_URL = (
    "https://api.twelvedata.com/time_series"
)
COINBASE_CANDLES_URL = (
    "https://api.exchange.coinbase.com/products"
)
COINBASE_TICKER_URL = (
    "https://api.exchange.coinbase.com/products"
)
# ============================================================
# TIMEFRAMES
# ============================================================
TIMEFRAME_TO_TWELVE = {
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}
TIMEFRAME_ALIASES = {
    "H4": "H4",
    "4H": "H4",
    "4h": "H4",
    "4hour": "H4",
    "H1": "H1",
    "1H": "H1",
    "1h": "H1",
    "1hour": "H1",
    "M15": "M15",
    "15M": "M15",
    "15MIN": "M15",
    "15min": "M15",
    "M5": "M5",
    "5M": "M5",
    "5MIN": "M5",
    "5min": "M5",
}
# ============================================================
# CRYPTO
# ============================================================
CRYPTO_PRODUCT_MAP = {
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "SOL/USD": "SOL-USD",
    "BNB/USD": "BNB-USD",
    "XRP/USD": "XRP-USD",
}
# ============================================================
# CACHE
# ============================================================
CACHE_TTL_SECONDS = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 60,
}
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
# ============================================================
# TWELVE DATA RATE LIMIT
# ============================================================
# Intervalle minimal entre deux appels Twelve Data.
TWELVE_MIN_REQUEST_INTERVAL = float(
    os.getenv(
        "TWELVE_MIN_REQUEST_INTERVAL",
        "8"
    )
)
# Cooldown après HTTP 429.
TWELVE_RATE_LIMIT_COOLDOWN = int(
    os.getenv(
        "TWELVE_RATE_LIMIT_COOLDOWN",
        "60"
    )
)
# Cooldown lorsque le quota journalier est atteint.
TWELVE_DAILY_QUOTA_COOLDOWN = int(
    os.getenv(
        "TWELVE_DAILY_QUOTA_COOLDOWN",
        str(24 * 60 * 60)
    )
)
_last_twelve_request = 0.0
_twelve_rate_locked_until = 0.0
_twelve_daily_locked_until = 0.0
_twelve_lock = threading.Lock()
# ============================================================
# HTTP
# ============================================================
REQUEST_TIMEOUT = int(
    os.getenv(
        "MARKET_DATA_TIMEOUT",
        "15"
    )
)
MAX_RETRIES_NON_429 = 2
# ============================================================
# OUTILS
# ============================================================
def normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()
def normalize_timeframe(timeframe: str) -> str:
    value = str(timeframe or "").strip()
    if value in TIMEFRAME_ALIASES:
        return TIMEFRAME_ALIASES[value]
    upper = value.upper()
    if upper in TIMEFRAME_ALIASES:
        return TIMEFRAME_ALIASES[upper]
    raise ValueError(
        f"Timeframe invalide : {timeframe}. "
        f"Valeurs autorisées : H4, H1, M15, M5"
    )
def is_crypto(symbol: str) -> bool:
    return normalize_symbol(symbol) in CRYPTO_PRODUCT_MAP
def _now() -> float:
    return time.time()
# ============================================================
# CACHE
# ============================================================
def _cache_key(
    symbol: str,
    timeframe: str
) -> str:
    return (
        f"{normalize_symbol(symbol)}:"
        f"{normalize_timeframe(timeframe)}"
    )
def _get_cached(
    symbol: str,
    timeframe: str
) -> Optional[List[Dict[str, Any]]]:
    key = _cache_key(
        symbol,
        timeframe
    )
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        timestamp = item.get(
            "timestamp",
            0
        )
        candles = item.get(
            "candles"
        )
    ttl = CACHE_TTL_SECONDS.get(
        normalize_timeframe(timeframe),
        60
    )
    if _now() - timestamp <= ttl:
        return candles
    return None
def _set_cache(
    symbol: str,
    timeframe: str,
    candles: List[Dict[str, Any]]
):
    key = _cache_key(
        symbol,
        timeframe
    )
    with _cache_lock:
        _cache[key] = {
            "timestamp": _now(),
            "candles": candles,
        }
# ============================================================
# TWELVE DATA LOCK
# ============================================================
def _twelve_remaining_cooldown() -> int:
    now = _now()
    with _twelve_lock:
        rate_remaining = max(
            0,
            _twelve_rate_locked_until - now
        )
        quota_remaining = max(
            0,
            _twelve_daily_locked_until - now
        )
    return int(
        max(
            rate_remaining,
            quota_remaining
        )
    )
def twelve_data_available() -> bool:
    if not TWELVE_DATA_KEY:
        return False
    return (
        _twelve_remaining_cooldown()
        <= 0
    )
def _wait_twelve_request_slot():
    global _last_twelve_request
    with _twelve_lock:
        now = _now()
        elapsed = (
            now - _last_twelve_request
        )
        wait_time = (
            TWELVE_MIN_REQUEST_INTERVAL
            - elapsed
        )
        if wait_time > 0:
            time.sleep(wait_time)
        _last_twelve_request = _now()
def _lock_twelve_rate_limit(
    seconds: int
):
    global _twelve_rate_locked_until
    with _twelve_lock:
        until = (
            _now() + max(1, seconds)
        )
        if until > _twelve_rate_locked_until:
            _twelve_rate_locked_until = until
def _lock_twelve_daily_quota():
    global _twelve_daily_locked_until
    with _twelve_lock:
        _twelve_daily_locked_until = (
            _now()
            + TWELVE_DAILY_QUOTA_COOLDOWN
        )
def _extract_retry_after(
    response: requests.Response
) -> int:
    value = response.headers.get(
        "Retry-After"
    )
    if value:
        try:
            return max(
                1,
                int(float(value))
            )
        except Exception:
            pass
    return TWELVE_RATE_LIMIT_COOLDOWN
# ============================================================
# TWELVE DATA
# ============================================================
def _request_twelve_candles(
    symbol: str,
    interval: str,
    outputsize: int = 300,
) -> List[Dict[str, Any]]:
    if not TWELVE_DATA_KEY:
        logger.error(
            "DATA Twelve Data : "
            "TWELVE_DATA_KEY absente."
        )
        return []
    cooldown = (
        _twelve_remaining_cooldown()
    )
    if cooldown > 0:
        logger.warning(
            "DATA Twelve Data : "
            "rate limit cooldown (%ss).",
            cooldown,
        )
        return []
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": min(
            max(int(outputsize), 1),
            5000
        ),
        "apikey": TWELVE_DATA_KEY,
        "format": "JSON",
        "order": "ASC",
    }
    for attempt in range(
        MAX_RETRIES_NON_429 + 1
    ):
        try:
            _wait_twelve_request_slot()
            response = requests.get(
                TWELVE_DATA_BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.error(
                "DATA Twelve Data : "
                "erreur réseau : %s",
                exc,
            )
            if attempt < MAX_RETRIES_NON_429:
                time.sleep(
                    2 ** attempt
                )
                continue
            return []
        # ----------------------------------------------------
        # RATE LIMIT
        # ----------------------------------------------------
        if response.status_code == 429:
            cooldown = _extract_retry_after(
                response
            )
            _lock_twelve_rate_limit(
                cooldown
            )
            logger.warning(
                "DATA Twelve Data : "
                "HTTP 429 -> cooldown %ss.",
                cooldown,
            )
            # Aucun retry immédiat après 429.
            return []
        # ----------------------------------------------------
        # AUTRES ERREURS HTTP
        # ----------------------------------------------------
        if response.status_code >= 500:
            logger.warning(
                "DATA Twelve Data : "
                "HTTP %s.",
                response.status_code,
            )
            if attempt < MAX_RETRIES_NON_429:
                time.sleep(
                    2 ** attempt
                )
                continue
            return []
        if response.status_code != 200:
            logger.error(
                "DATA Twelve Data : "
                "HTTP %s.",
                response.status_code,
            )
            return []
        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------
        try:
            payload = response.json()
        except ValueError:
            logger.error(
                "DATA Twelve Data : "
                "réponse JSON invalide."
            )
            return []
        # ----------------------------------------------------
        # ERREUR API
        # ----------------------------------------------------
        if (
            isinstance(payload, dict)
            and payload.get("status") == "error"
        ):
            message = str(
                payload.get(
                    "message",
                    "Erreur Twelve Data."
                )
            )
            lower = message.lower()
            if any(
                word in lower
                for word in (
                    "credit",
                    "quota",
                    "limit",
                    "run out",
                )
            ):
                _lock_twelve_daily_quota()
                logger.error(
                    "DATA Twelve Data : "
                    "quota journalier atteint. "
                    "Cooldown 24h."
                )
                return []
            logger.error(
                "DATA Twelve Data : %s",
                message,
            )
            return []
        values = payload.get(
            "values",
            []
        )
        if not isinstance(
            values,
            list
        ):
            logger.error(
                "DATA Twelve Data : "
                "champ values invalide."
            )
            return []
        candles = []
        for row in values:
            try:
                candles.append(
                    {
                        "datetime": row.get(
                            "datetime"
                        ),
                        "open": float(
                            row["open"]
                        ),
                        "high": float(
                            row["high"]
                        ),
                        "low": float(
                            row["low"]
                        ),
                        "close": float(
                            row["close"]
                        ),
                        "volume": float(
                            row.get(
                                "volume",
                                0
                            ) or 0
                        ),
                    }
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue
        candles.sort(
            key=lambda x: str(
                x.get(
                    "datetime",
                    ""
                )
            )
        )
        # ----------------------------------------------------
        # DONNÉES VIDES
        # ----------------------------------------------------
        if not candles:
            # Ne pas générer de faux "0 chandelier"
            # lorsqu'une réponse vide est provoquée par
            # une limitation du fournisseur.
            if not twelve_data_available():
                return []
            logger.warning(
                "DATA Twelve Data %s %s : "
                "aucune donnée disponible.",
                symbol,
                interval,
            )
            return []
        return candles
    return []
# ============================================================
# COINBASE
# ============================================================
def _coinbase_granularity(
    timeframe: str
) -> int:
    tf = normalize_timeframe(
        timeframe
    )
    mapping = {
        "M5": 300,
        "M15": 900,
        "H1": 3600,
    }
    if tf not in mapping:
        raise ValueError(
            "Coinbase ne fournit pas "
            "directement H4. "
            "H4 est agrégé depuis H1."
        )
    return mapping[tf]
def _request_coinbase_candles(
    symbol: str,
    timeframe: str,
    limit: int = 300,
) -> List[Dict[str, Any]]:
    product = CRYPTO_PRODUCT_MAP.get(
        normalize_symbol(symbol)
    )
    if not product:
        return []
    tf = normalize_timeframe(
        timeframe
    )
    if tf == "H4":
        h1 = _request_coinbase_candles(
            symbol,
            "H1",
            min(
                max(limit * 4, 100),
                300
            )
        )
        return _aggregate_h1_to_h4(
            h1,
            limit
        )
    granularity = (
        _coinbase_granularity(tf)
    )
    url = (
        f"{COINBASE_CANDLES_URL}/"
        f"{product}/candles"
    )
    params = {
        "granularity": granularity,
    }
    try:
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Accept": "application/json"
            },
        )
    except requests.RequestException as exc:
        logger.error(
            "DATA Coinbase %s %s : %s",
            symbol,
            tf,
            exc,
        )
        return []
    if response.status_code != 200:
        logger.error(
            "DATA Coinbase %s %s : "
            "HTTP %s",
            symbol,
            tf,
            response.status_code,
        )
        return []
    try:
        rows = response.json()
    except ValueError:
        logger.error(
            "DATA Coinbase : "
            "JSON invalide."
        )
        return []
    if not isinstance(rows, list):
        return []
    candles = []
    for row in rows:
        try:
            # Coinbase :
            # [time, low, high, open, close, volume]
            timestamp = int(
                row[0]
            )
            candles.append(
                {
                    "datetime": (
                        datetime.fromtimestamp(
                            timestamp,
                            tz=timezone.utc
                        ).isoformat()
                    ),
                    "open": float(row[3]),
                    "high": float(row[2]),
                    "low": float(row[1]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        except (
            IndexError,
            TypeError,
            ValueError,
        ):
            continue
    candles.sort(
        key=lambda x: str(
            x["datetime"]
        )
    )
    return candles[-limit:]
def _aggregate_h1_to_h4(
    candles: List[Dict[str, Any]],
    limit: int
) -> List[Dict[str, Any]]:
    if not candles:
        return []
    buckets = {}
    for candle in candles:
        try:
            dt = datetime.fromisoformat(
                str(
                    candle["datetime"]
                ).replace(
                    "Z",
                    "+00:00"
                )
            )
            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )
            bucket_hour = (
                dt.hour // 4
            ) * 4
            bucket = dt.replace(
                hour=bucket_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            key = bucket.isoformat()
            buckets.setdefault(
                key,
                []
            ).append(candle)
        except Exception:
            continue
    result = []
    for key in sorted(buckets):
        group = buckets[key]
        if not group:
            continue
        result.append(
            {
                "datetime": key,
                "open": group[0]["open"],
                "high": max(
                    x["high"]
                    for x in group
                ),
                "low": min(
                    x["low"]
                    for x in group
                ),
                "close": group[-1]["close"],
                "volume": sum(
                    x.get(
                        "volume",
                        0
                    )
                    for x in group
                ),
            }
        )
    return result[-limit:]
# ============================================================
# PUBLIC : GET CANDLES
# ============================================================
def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 300,
) -> List[Dict[str, Any]]:
    symbol = normalize_symbol(
        symbol
    )
    timeframe = normalize_timeframe(
        timeframe
    )
    cached = _get_cached(
        symbol,
        timeframe
    )
    if cached:
        return cached[-limit:]
    # --------------------------------------------------------
    # CRYPTO -> COINBASE UNIQUEMENT
    # --------------------------------------------------------
    if is_crypto(symbol):
        candles = (
            _request_coinbase_candles(
                symbol,
                timeframe,
                limit
            )
        )
        if candles:
            _set_cache(
                symbol,
                timeframe,
                candles
            )
        else:
            # Coinbase uniquement :
            # log explicite, sans fallback.
            logger.warning(
                "DATA Coinbase %s %s : "
                "aucune donnée disponible.",
                symbol,
                timeframe,
            )
        return candles
    # --------------------------------------------------------
    # FOREX/XAU -> TWELVE DATA UNIQUEMENT
    # --------------------------------------------------------
    interval = (
        TIMEFRAME_TO_TWELVE[
            timeframe
        ]
    )
    candles = _request_twelve_candles(
        symbol,
        interval,
        limit
    )
    if candles:
        _set_cache(
            symbol,
            timeframe,
            candles
        )
    else:
        # IMPORTANT :
        # Si Twelve Data est en cooldown, ne pas produire
        # un faux "0 chandelier".
        #
        # Le cooldown a déjà été journalisé par
        # _request_twelve_candles().
        if twelve_data_available():
            logger.warning(
                "DATA %s %s : "
                "aucune donnée disponible.",
                symbol,
                timeframe,
            )
    return candles
# ============================================================
# PUBLIC : LATEST PRICE
# ============================================================
def get_latest_price(
    symbol: str
) -> Optional[float]:
    symbol = normalize_symbol(
        symbol
    )
    # --------------------------------------------------------
    # CRYPTO -> COINBASE
    # --------------------------------------------------------
    if is_crypto(symbol):
        product = (
            CRYPTO_PRODUCT_MAP[
                symbol
            ]
        )
        url = (
            f"{COINBASE_TICKER_URL}/"
            f"{product}/ticker"
        )
        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "Accept": "application/json"
                },
            )
            if response.status_code != 200:
                logger.error(
                    "PRICE Coinbase %s : "
                    "HTTP %s",
                    symbol,
                    response.status_code,
                )
                return None
            payload = response.json()
            return float(
                payload["price"]
            )
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            logger.error(
                "PRICE Coinbase %s : %s",
                symbol,
                exc,
            )
            return None
    # --------------------------------------------------------
    # FOREX/XAU -> TWELVE DATA
    # --------------------------------------------------------
    if not TWELVE_DATA_KEY:
        logger.error(
            "PRICE Twelve Data : "
            "TWELVE_DATA_KEY absente."
        )
        return None
    cooldown = (
        _twelve_remaining_cooldown()
    )
    if cooldown > 0:
        logger.warning(
            "PRICE Twelve Data : "
            "cooldown (%ss).",
            cooldown,
        )
        return None
    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 1,
        "apikey": TWELVE_DATA_KEY,
        "format": "JSON",
    }
    try:
        _wait_twelve_request_slot()
        response = requests.get(
            TWELVE_DATA_BASE_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.error(
            "PRICE Twelve Data %s : %s",
            symbol,
            exc,
        )
        return None
    if response.status_code == 429:
        cooldown = _extract_retry_after(
            response
        )
        _lock_twelve_rate_limit(
            cooldown
        )
        logger.warning(
            "PRICE Twelve Data : "
            "HTTP 429 -> cooldown %ss.",
            cooldown,
        )
        return None
    if response.status_code != 200:
        logger.error(
            "PRICE Twelve Data %s : "
            "HTTP %s",
            symbol,
            response.status_code,
        )
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if (
        isinstance(payload, dict)
        and payload.get("status") == "error"
    ):
        message = str(
            payload.get(
                "message",
                ""
            )
        )
        if any(
            word in message.lower()
            for word in (
                "credit",
                "quota",
                "limit",
                "run out",
            )
        ):
            _lock_twelve_daily_quota()
        logger.error(
            "PRICE Twelve Data %s : %s",
            symbol,
            message,
        )
        return None
    values = payload.get(
        "values",
        []
    )
    if not values:
        return None
    try:
        return float(
            values[0]["close"]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return None
# ============================================================
# STATUS FOURNISSEURS
# ============================================================
def get_provider_status() -> Dict[str, Any]:
    cooldown = (
        _twelve_remaining_cooldown()
    )
    return {
        "twelve_data_configured": bool(
            TWELVE_DATA_KEY
        ),
        "twelve_data_available": (
            bool(TWELVE_DATA_KEY)
            and cooldown <= 0
        ),
        "twelve_data_cooldown": cooldown,
        "crypto_provider": "Coinbase",
        "forex_provider": "Twelve Data",
    }
# ============================================================
# ALIAS
# ============================================================
get_price = get_latest_price
# Permet :
# from market_data import market_data
market_data = sys.modules[
    __name__
]