"""
NOVA TRADE AI
market_data.py
SOURCE DES DONNÉES
------------------
FOREX + XAU/USD
    -> Twelve Data uniquement
CRYPTO
    -> Coinbase Exchange API publique uniquement
    -> aucune clé API nécessaire
TIMEFRAMES
----------
H4  -> 4h
H1  -> 1h
M15 -> 15m
M5  -> 5m
IMPORTANT
---------
Il n'y a AUCUN fallback entre les fournisseurs.
Crypto ne passe jamais par Twelve Data.
Forex/XAU ne passe jamais par Coinbase.
"""
from __future__ import annotations
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
# ============================================================
# LOGGER
# ============================================================
logger = logging.getLogger(__name__)
# ============================================================
# API
# ============================================================
TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"
# Coinbase Exchange API publique
COINBASE_CANDLES_URL = (
    "https://api.exchange.coinbase.com/products/{product_id}/candles"
)
COINBASE_TICKER_URL = (
    "https://api.exchange.coinbase.com/products/{product_id}/ticker"
)
# ============================================================
# PARAMÈTRES HTTP
# ============================================================
TWELVE_TIMEOUT = 15
COINBASE_TIMEOUT = 15
MAX_RETRIES = 3
TWELVE_RETRY_DELAYS = (5, 15, 30)
COINBASE_RETRY_DELAYS = (2, 5, 10)
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
    "H4": 14400,   # 4 heures
    "H1": 3600,    # 1 heure
    "M15": 900,    # 15 minutes
    "M5": 300,     # 5 minutes
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
STALE_MAX_AGE = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 5 * 60,
}
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.RLock()
# ============================================================
# LIMITATION TWELVE DATA
# ============================================================
TWELVE_MIN_REQUEST_INTERVAL = 2.0
_last_twelve_request = 0.0
_twelve_lock = threading.Lock()
_twelve_quota_blocked_until = 0.0
# ============================================================
# STATISTIQUES
# ============================================================
_stats = {
    "twelve_requests": 0,
    "twelve_success": 0,
    "twelve_errors": 0,
    "coinbase_requests": 0,
    "coinbase_success": 0,
    "coinbase_errors": 0,
    "cache_hits": 0,
    "cache_stale_hits": 0,
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
# NORMALISATION
# ============================================================
def _normalize_symbol(symbol: str) -> str:
    if symbol is None:
        return ""
    return str(symbol).strip().upper().replace("-", "/")
def _normalize_timeframe(timeframe: str) -> str:
    if timeframe is None:
        raise ValueError("Timeframe manquant.")
    tf = str(timeframe).strip().upper()
    aliases = {
        "4H": "H4",
        "H4": "H4",
        "1H": "H1",
        "H1": "H1",
        "15M": "M15",
        "15MIN": "M15",
        "M15": "M15",
        "5M": "M5",
        "5MIN": "M5",
        "M5": "M5",
    }
    if tf not in aliases:
        raise ValueError(
            f"Timeframe invalide : {timeframe}. "
            f"Valeurs autorisées : H4, H1, M15, M5."
        )
    return aliases[tf]
def _is_crypto_symbol(symbol: str) -> bool:
    return _normalize_symbol(symbol) in CRYPTO_SYMBOL_MAP
def is_crypto(symbol: str) -> bool:
    return _is_crypto_symbol(symbol)
def get_data_source(symbol: str) -> str:
    """
    Retourne le fournisseur utilisé pour le symbole.
    """
    symbol = _normalize_symbol(symbol)
    if _is_crypto_symbol(symbol):
        return "COINBASE"
    return "TWELVE_DATA"
# ============================================================
# API KEYS
# ============================================================
def _get_twelve_data_api_key() -> str:
    import os
    return os.getenv("TWELVE_DATA_API_KEY", "").strip()
# ============================================================
# TIMESTAMPS
# ============================================================
def _parse_timestamp(value: Any) -> datetime:
    """
    Convertit différents formats de timestamp en datetime UTC.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = datetime.strptime(
                text,
                "%Y-%m-%d %H:%M:%S",
            )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
# ============================================================
# CACHE
# ============================================================
def _cache_key(symbol: str, timeframe: str) -> str:
    return f"{_normalize_symbol(symbol)}::{_normalize_timeframe(timeframe)}"
def _get_cached_candles(
    symbol: str,
    timeframe: str,
) -> Optional[List[Dict[str, Any]]]:
    key = _cache_key(symbol, timeframe)
    now = time.time()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        age = now - item["timestamp"]
        if age <= CACHE_TTL[_normalize_timeframe(timeframe)]:
            _stats["cache_hits"] += 1
            return list(item["candles"])
    return None
def _get_stale_cache(
    symbol: str,
    timeframe: str,
) -> Optional[List[Dict[str, Any]]]:
    key = _cache_key(symbol, timeframe)
    now = time.time()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        age = now - item["timestamp"]
        if age <= STALE_MAX_AGE[_normalize_timeframe(timeframe)]:
            _stats["cache_stale_hits"] += 1
            logger.warning(
                "CACHE STALE utilisé : %s %s | âge=%.0fs",
                symbol,
                timeframe,
                age,
            )
            return list(item["candles"])
    return None
def _set_cached_candles(
    symbol: str,
    timeframe: str,
    candles: List[Dict[str, Any]],
) -> None:
    key = _cache_key(symbol, timeframe)
    with _cache_lock:
        _cache[key] = {
            "timestamp": time.time(),
            "candles": list(candles),
        }
def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
# ============================================================
# TWELVE DATA RATE LIMIT
# ============================================================
def _wait_twelve_rate_limit() -> None:
    global _last_twelve_request
    with _twelve_lock:
        now = time.monotonic()
        elapsed = now - _last_twelve_request
        if elapsed < TWELVE_MIN_REQUEST_INTERVAL:
            time.sleep(
                TWELVE_MIN_REQUEST_INTERVAL - elapsed
            )
        _last_twelve_request = time.monotonic()
# ============================================================
# TWELVE DATA QUOTA
# ============================================================
def _is_twelve_quota_error(message: str) -> bool:
    text = str(message).lower()
    keywords = (
        "run out of api credits",
        "api credits",
        "current limit",
        "quota",
        "credits were used",
    )
    return any(
        keyword in text
        for keyword in keywords
    )
def is_twelve_data_blocked() -> bool:
    return time.time() < _twelve_quota_blocked_until
def _block_twelve_data_for_day() -> None:
    global _twelve_quota_blocked_until
    # Blocage large pour éviter de marteler Twelve Data
    _twelve_quota_blocked_until = (
        time.time() + 24 * 60 * 60
    )
# ============================================================
# NORMALISATION DES CANDLE
# ============================================================
def _make_candle(
    timestamp: Any,
    open_price: Any,
    high: Any,
    low: Any,
    close: Any,
    volume: Any = 0.0,
) -> Dict[str, Any]:
    dt = _parse_timestamp(timestamp)
    return {
        "datetime": dt,
        "timestamp": dt.timestamp(),
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume or 0.0),
    }
# ============================================================
# TWELVE DATA
# ============================================================
def _request_twelve_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> List[Dict[str, Any]]:
    global _stats
    symbol = _normalize_symbol(symbol)
    timeframe = _normalize_timeframe(timeframe)
    if is_twelve_data_blocked():
        raise RuntimeError(
            "Twelve Data temporairement bloqué : "
            "quota journalier atteint."
        )
    api_key = _get_twelve_data_api_key()
    if not api_key:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY non configurée."
        )
    interval = TIMEFRAME_MAP[timeframe]
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": min(int(outputsize), 5000),
        "apikey": api_key,
        "format": "JSON",
    }
    last_error = None
    for attempt in range(MAX_RETRIES):
        _wait_twelve_rate_limit()
        try:
            _stats["twelve_requests"] += 1
            response = requests.get(
                TWELVE_DATA_URL,
                params=params,
                timeout=TWELVE_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(
                    "Réponse Twelve Data invalide."
                )
            if data.get("status") == "error":
                message = data.get(
                    "message",
                    "Erreur Twelve Data inconnue.",
                )
                if _is_twelve_quota_error(message):
                    _block_twelve_data_for_day()
                    raise RuntimeError(
                        f"Twelve Data : {message}"
                    )
                raise RuntimeError(
                    f"Twelve Data : {message}"
                )
            values = data.get("values")
            if not values:
                raise RuntimeError(
                    "Twelve Data : aucune donnée reçue."
                )
            candles: List[Dict[str, Any]] = []
            for item in values:
                try:
                    candle = _make_candle(
                        item["datetime"],
                        item["open"],
                        item["high"],
                        item["low"],
                        item["close"],
                        item.get("volume", 0.0),
                    )
                    candles.append(candle)
                except Exception as exc:
                    logger.warning(
                        "Twelve Data candle ignorée : %s",
                        exc,
                    )
            candles.sort(
                key=lambda x: x["timestamp"]
            )
            if not candles:
                raise RuntimeError(
                    "Twelve Data : chandeliers invalides."
                )
            _stats["twelve_success"] += 1
            return candles
        except Exception as exc:
            last_error = exc
            if is_twelve_data_blocked():
                raise
            if attempt < MAX_RETRIES - 1:
                time.sleep(
                    TWELVE_RETRY_DELAYS[attempt]
                )
    _stats["twelve_errors"] += 1
    raise RuntimeError(
        str(last_error)
        if last_error
        else "Erreur Twelve Data inconnue."
    )
# ============================================================
# COINBASE
# ============================================================
def _request_coinbase_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> List[Dict[str, Any]]:
    symbol = _normalize_symbol(symbol)
    timeframe = _normalize_timeframe(timeframe)
    if symbol not in CRYPTO_SYMBOL_MAP:
        raise ValueError(
            f"Crypto non supportée par Coinbase : {symbol}"
        )
    product_id = CRYPTO_SYMBOL_MAP[symbol]
    granularity = COINBASE_GRANULARITY[timeframe]
    url = COINBASE_CANDLES_URL.format(
        product_id=product_id
    )
    # Coinbase limite le nombre de bougies par requête.
    # 300 bougies restent largement sous la limite.
    limit = min(int(outputsize), 300)
    # On demande une fenêtre suffisamment grande.
    end = int(time.time())
    start = end - (granularity * limit)
    params = {
        "start": datetime.fromtimestamp(
            start,
            tz=timezone.utc,
        ).isoformat(),
        "end": datetime.fromtimestamp(
            end,
            tz=timezone.utc,
        ).isoformat(),
        "granularity": granularity,
    }
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            _stats["coinbase_requests"] += 1
            response = requests.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NOVA-TRADE-AI/1.0",
                },
                timeout=COINBASE_TIMEOUT,
            )
            if response.status_code >= 400:
                body = response.text[:1000]
                raise RuntimeError(
                    f"Coinbase : HTTP "
                    f"{response.status_code}: {body}"
                )
            data = response.json()
            if not isinstance(data, list):
                raise RuntimeError(
                    "Coinbase : réponse candles invalide."
                )
            candles: List[Dict[str, Any]] = []
            for row in data:
                if not isinstance(row, list):
                    continue
                if len(row) < 6:
                    continue
                try:
                    # Coinbase :
                    # [time, low, high, open, close, volume]
                    candle = _make_candle(
                        row[0],
                        row[3],
                        row[2],
                        row[1],
                        row[4],
                        row[5],
                    )
                    candles.append(candle)
                except Exception as exc:
                    logger.warning(
                        "Coinbase candle ignorée : %s",
                        exc,
                    )
            candles.sort(
                key=lambda x: x["timestamp"]
            )
            if not candles:
                raise RuntimeError(
                    f"Coinbase : 0 chandelier "
                    f"pour {symbol} {timeframe}."
                )
            # Coinbase peut retourner légèrement plus
            # de données que demandé.
            candles = candles[-limit:]
            _stats["coinbase_success"] += 1
            return candles
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(
                    COINBASE_RETRY_DELAYS[attempt]
                )
    _stats["coinbase_errors"] += 1
    raise RuntimeError(
        str(last_error)
        if last_error
        else "Erreur Coinbase inconnue."
    )
# ============================================================
# ROUTAGE CENTRAL
# ============================================================
def _request_market_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 300,
) -> List[Dict[str, Any]]:
    symbol = _normalize_symbol(symbol)
    timeframe = _normalize_timeframe(timeframe)
    # --------------------------------------------------------
    # CRYPTO -> COINBASE UNIQUEMENT
    # --------------------------------------------------------
    if _is_crypto_symbol(symbol):
        return _request_coinbase_candles(
            symbol,
            timeframe,
            outputsize,
        )
    # --------------------------------------------------------
    # FOREX + XAU -> TWELVE DATA UNIQUEMENT
    # --------------------------------------------------------
    return _request_twelve_candles(
        symbol,
        timeframe,
        outputsize,
    )
# ============================================================
# PUBLIC API
# ============================================================
def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 300,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    symbol = _normalize_symbol(symbol)
    timeframe = _normalize_timeframe(timeframe)
    if limit <= 0:
        return []
    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------
    if not force_refresh:
        cached = _get_cached_candles(
            symbol,
            timeframe,
        )
        if cached:
            return cached[-limit:]
    # --------------------------------------------------------
    # API
    # --------------------------------------------------------
    try:
        candles = _request_market_candles(
            symbol,
            timeframe,
            max(limit, 300),
        )
        if candles:
            _set_cached_candles(
                symbol,
                timeframe,
                candles,
            )
            return candles[-limit:]
    except Exception:
        # ----------------------------------------------------
        # STALE CACHE
        # ----------------------------------------------------
        stale = _get_stale_cache(
            symbol,
            timeframe,
        )
        if stale:
            return stale[-limit:]
        raise
    return []
def get_latest_price(
    symbol: str,
) -> float:
    symbol = _normalize_symbol(symbol)
    # --------------------------------------------------------
    # CRYPTO -> COINBASE
    # --------------------------------------------------------
    if _is_crypto_symbol(symbol):
        product_id = CRYPTO_SYMBOL_MAP[symbol]
        url = COINBASE_TICKER_URL.format(
            product_id=product_id
        )
        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "NOVA-TRADE-AI/1.0",
            },
            timeout=COINBASE_TIMEOUT,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Coinbase ticker HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )
        data = response.json()
        price = data.get("price")
        if price is None:
            raise RuntimeError(
                f"Coinbase : prix introuvable pour {symbol}."
            )
        return float(price)
    # --------------------------------------------------------
    # FOREX / XAU
    # --------------------------------------------------------
    candles = get_candles(
        symbol,
        "M5",
        limit=1,
    )
    if not candles:
        raise RuntimeError(
            f"Prix indisponible pour {symbol}."
        )
    return float(candles[-1]["close"])
def get_price(symbol: str) -> float:
    return get_latest_price(symbol)
# ============================================================
# INFORMATIONS
# ============================================================
def get_stats() -> Dict[str, Any]:
    with _cache_lock:
        cache_size = len(_cache)
    return {
        **_stats,
        "cache_size": cache_size,
        "twelve_data_blocked": is_twelve_data_blocked(),
    }
def reset_stats() -> None:
    global _stats
    _stats = {
        "twelve_requests": 0,
        "twelve_success": 0,
        "twelve_errors": 0,
        "coinbase_requests": 0,
        "coinbase_success": 0,
        "coinbase_errors": 0,
        "cache_hits": 0,
        "cache_stale_hits": 0,
    }
# ============================================================
# TEST RAPIDE
# ============================================================
def test_symbol(
    symbol: str,
    timeframe: str = "M15",
) -> Dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    timeframe = _normalize_timeframe(timeframe)
    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": get_data_source(symbol),
        "success": False,
        "candles": 0,
        "last_price": None,
        "error": None,
    }
    try:
        candles = get_candles(
            symbol,
            timeframe,
            limit=10,
            force_refresh=True,
        )
        result["success"] = bool(candles)
        result["candles"] = len(candles)
        if candles:
            result["last_price"] = candles[-1]["close"]
    except Exception as exc:
        result["error"] = str(exc)
    return result
# ============================================================
# OBJET GLOBAL COMPATIBLE AVEC PIPELINE
# ============================================================
# Permet à :
#
# from market_data import market_data
#
# de fonctionner même si ce fichier est un module simple.
market_data = sys.modules[__name__]
# ============================================================
# LOG DE DÉMARRAGE
# ============================================================
logger.info(
    "Market Data initialisé | "
    "FOREX/XAU=Twelve Data | "
    "CRYPTO=Coinbase | "
    "Fallback croisé=OFF"
)