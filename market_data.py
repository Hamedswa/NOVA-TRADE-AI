import os
import time
from datetime import datetime, timezone
from threading import Lock

import requests

from core.models import Candle


BASE_URL = "https://api.twelvedata.com/time_series"

TIMEFRAME_MAP = {
    "D1": "1day",
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}

# -------------------------------------------------------------------
# PARAMÈTRES API
# -------------------------------------------------------------------

REQUEST_TIMEOUT = 15

# Nombre maximum de tentatives pour une erreur temporaire.
MAX_RETRIES = 3

# Attentes progressives.
RETRY_DELAYS = (5, 15, 30)

# Petit cache local pour éviter de redemander immédiatement
# les mêmes données à Twelve Data.
CACHE_TTL_SECONDS = 20

# Protection contre plusieurs appels simultanés.
_CACHE_LOCK = Lock()

# {
#     (symbol, timeframe, outputsize): {
#         "timestamp": ...,
#         "candles": [...]
#     }
# }
_CANDLE_CACHE = {}


def _get_api_key() -> str:
    """
    Récupère la clé Twelve Data depuis l'environnement.

    La clé n'est jamais affichée dans les logs ou les messages
    d'erreur.
    """

    key = os.getenv("TWELVE_DATA_API_KEY", "").strip()

    if not key:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY n'est pas configurée."
        )

    return key


def _parse_timestamp(value: str) -> datetime:
    """
    Convertit une date Twelve Data en datetime UTC.
    """

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
        "Date invalide reçue depuis Twelve Data."
    )


def _get_cached_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
):
    """
    Retourne les données du cache si elles sont encore valides.
    """

    cache_key = (
        symbol.upper(),
        timeframe.upper(),
        outputsize,
    )

    now = time.time()

    with _CACHE_LOCK:

        cached = _CANDLE_CACHE.get(cache_key)

        if not cached:
            return None

        age = now - cached["timestamp"]

        if age > CACHE_TTL_SECONDS:
            del _CANDLE_CACHE[cache_key]
            return None

        return cached["candles"]


def _save_cached_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
    candles: list[Candle],
):
    """
    Sauvegarde les bougies dans le cache.
    """

    cache_key = (
        symbol.upper(),
        timeframe.upper(),
        outputsize,
    )

    with _CACHE_LOCK:

        _CANDLE_CACHE[cache_key] = {
            "timestamp": time.time(),
            "candles": candles,
        }


def _parse_api_error(response: requests.Response) -> str:
    """
    Extrait un message d'erreur Twelve Data sans jamais exposer
    l'URL contenant la clé API.
    """

    try:

        data = response.json()

        message = data.get("message")

        if message:
            return str(message)

        code = data.get("code")

        if code:
            return f"Erreur Twelve Data (code {code})."

    except ValueError:
        pass

    if response.status_code == 429:
        return "Limite de requêtes Twelve Data atteinte."

    if response.status_code == 401:
        return "Clé Twelve Data invalide ou non autorisée."

    if response.status_code == 403:
        return "Accès Twelve Data refusé."

    if response.status_code >= 500:
        return "Service Twelve Data temporairement indisponible."

    return (
        f"Erreur Twelve Data HTTP {response.status_code}."
    )


def _request_candles(
    symbol: str,
    timeframe: str,
    outputsize: int,
) -> list[Candle]:

    api_key = _get_api_key()

    params = {
        "symbol": symbol,
        "interval": TIMEFRAME_MAP[timeframe],
        "outputsize": outputsize,
        "apikey": api_key,
    }

    last_message = "Erreur inconnue."

    for attempt in range(MAX_RETRIES):

        try:

            response = requests.get(
                BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            # -------------------------------------------------------
            # RATE LIMIT
            # -------------------------------------------------------

            if response.status_code == 429:

                last_message = (
                    "Limite Twelve Data atteinte (HTTP 429)."
                )

                # Twelve Data peut éventuellement fournir
                # Retry-After.
                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    wait_seconds = int(
                        retry_after
                    )
                except (TypeError, ValueError):

                    wait_seconds = RETRY_DELAYS[
                        min(
                            attempt,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]

                if attempt < MAX_RETRIES - 1:

                    time.sleep(
                        max(
                            1,
                            min(wait_seconds, 60),
                        )
                    )

                    continue

                break

            # -------------------------------------------------------
            # AUTRES ERREURS HTTP
            # -------------------------------------------------------

            if response.status_code >= 400:

                last_message = _parse_api_error(
                    response
                )

                # Les erreurs 5xx peuvent être temporaires.
                if (
                    response.status_code >= 500
                    and attempt < MAX_RETRIES - 1
                ):

                    time.sleep(
                        RETRY_DELAYS[
                            min(
                                attempt,
                                len(RETRY_DELAYS) - 1,
                            )
                        ]
                    )

                    continue

                break

            # -------------------------------------------------------
            # JSON
            # -------------------------------------------------------

            try:

                data = response.json()

            except ValueError:

                last_message = (
                    "Réponse Twelve Data invalide."
                )

                if attempt < MAX_RETRIES - 1:

                    time.sleep(
                        RETRY_DELAYS[
                            min(
                                attempt,
                                len(RETRY_DELAYS) - 1,
                            )
                        ]
                    )

                    continue

                break

            # -------------------------------------------------------
            # ERREUR API DANS LE JSON
            # -------------------------------------------------------

            if data.get("status") == "error":

                last_message = str(
                    data.get(
                        "message",
                        "Erreur Twelve Data.",
                    )
                )

                # Si Twelve Data signale une limite dans le JSON,
                # on attend avant de retenter.
                message_lower = last_message.lower()

                is_rate_limit = any(
                    word in message_lower
                    for word in (
                        "limit",
                        "too many",
                        "rate",
                        "quota",
                    )
                )

                if (
                    is_rate_limit
                    and attempt < MAX_RETRIES - 1
                ):

                    time.sleep(
                        RETRY_DELAYS[
                            min(
                                attempt,
                                len(RETRY_DELAYS) - 1,
                            )
                        ]
                    )

                    continue

                break

            # -------------------------------------------------------
            # VALEURS
            # -------------------------------------------------------

            values = data.get("values", [])

            if not values:

                last_message = (
                    f"Aucune bougie reçue pour "
                    f"{symbol} {timeframe}."
                )

                break

            candles = []

            for item in reversed(values):

                try:

                    candle = Candle(
                        timestamp=_parse_timestamp(
                            str(item["datetime"])
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

                    candles.append(candle)

                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ) as exc:

                    raise RuntimeError(
                        "Bougie Twelve Data invalide."
                    ) from exc

            if not candles:

                raise RuntimeError(
                    f"Aucune bougie valide pour "
                    f"{symbol} {timeframe}."
                )

            return candles

        except requests.Timeout:

            last_message = (
                "Timeout lors de la connexion "
                "à Twelve Data."
            )

            if attempt < MAX_RETRIES - 1:

                time.sleep(
                    RETRY_DELAYS[
                        min(
                            attempt,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]
                )

                continue

        except requests.ConnectionError:

            last_message = (
                "Impossible de joindre Twelve Data."
            )

            if attempt < MAX_RETRIES - 1:

                time.sleep(
                    RETRY_DELAYS[
                        min(
                            attempt,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]
                )

                continue

        except RuntimeError:

            raise

        except Exception:

            last_message = (
                "Erreur inattendue lors de la "
                "récupération des données."
            )

            if attempt < MAX_RETRIES - 1:

                time.sleep(
                    RETRY_DELAYS[
                        min(
                            attempt,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]
                )

                continue

    raise RuntimeError(
        f"Impossible de récupérer les données "
        f"{symbol} {timeframe}: {last_message}"
    )


def get_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 100,
) -> list[Candle]:
    """
    Récupère les bougies Twelve Data.

    Protection :
    - validation du timeframe
    - cache local
    - retry progressif
    - gestion du HTTP 429
    - aucune fuite de clé API
    """

    symbol = symbol.strip().upper()
    timeframe = timeframe.strip().upper()

    if not symbol:

        raise ValueError(
            "Symbole invalide."
        )

    if timeframe not in TIMEFRAME_MAP:

        raise ValueError(
            f"Timeframe invalide : {timeframe}. "
            f"Valeurs autorisées : "
            f"{list(TIMEFRAME_MAP.keys())}"
        )

    if outputsize < 1:

        raise ValueError(
            "outputsize doit être supérieur à 0."
        )

    # ---------------------------------------------------------------
    # CACHE
    # ---------------------------------------------------------------

    cached = _get_cached_candles(
        symbol,
        timeframe,
        outputsize,
    )

    if cached is not None:

        return cached

    # ---------------------------------------------------------------
    # API
    # ---------------------------------------------------------------

    candles = _request_candles(
        symbol,
        timeframe,
        outputsize,
    )

    # ---------------------------------------------------------------
    # SAUVEGARDE CACHE
    # ---------------------------------------------------------------

    _save_cached_candles(
        symbol,
        timeframe,
        outputsize,
        candles,
    )

    return candles


def get_latest_price(symbol: str) -> float:
    """
    Retourne le dernier prix disponible à partir des bougies M5.
    """

    candles = get_candles(
        symbol,
        "M5",
        outputsize=2,
    )

    if not candles:

        raise RuntimeError(
            f"Prix indisponible pour {symbol}."
        )

    return candles[-1].close