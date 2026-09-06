import os
import time
from datetime import datetime, timezone

import requests

from core.models import Candle


TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

BASE_URL = "https://api.twelvedata.com/time_series"

TIMEFRAME_MAP = {
    "D1": "1day",
    "H4": "4h",
    "H1": "1h",
    "M15": "15min",
    "M5": "5min",
}


def _parse_timestamp(value: str) -> datetime:
    """
    Convertit la date Twelve Data en datetime UTC.
    """

    value = value.strip()

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(
        f"Date invalide reçue : {value}"
    )


def get_candles(
    symbol: str,
    timeframe: str,
    outputsize: int = 100,
) -> list[Candle]:

    if not TWELVE_DATA_API_KEY:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY n'est pas configurée."
        )

    timeframe = timeframe.upper()

    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(
            f"Timeframe invalide : {timeframe}"
        )

    params = {
        "symbol": symbol,
        "interval": TIMEFRAME_MAP[timeframe],
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
    }

    last_error = None

    for attempt in range(3):

        try:

            response = requests.get(
                BASE_URL,
                params=params,
                timeout=15,
            )

            response.raise_for_status()

            data = response.json()

            if "status" in data and data["status"] == "error":
                raise RuntimeError(
                    data.get(
                        "message",
                        "Erreur Twelve Data.",
                    )
                )

            values = data.get("values", [])

            if not values:
                raise RuntimeError(
                    f"Aucune bougie reçue pour {symbol} {timeframe}."
                )

            candles = []

            for item in reversed(values):

                candles.append(
                    Candle(
                        timestamp=_parse_timestamp(
                            item["datetime"]
                        ),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=float(
                            item.get("volume", 0) or 0
                        ),
                    )
                )

            return candles

        except Exception as exc:

            last_error = exc

            if attempt < 2:
                time.sleep(1 + attempt)

    raise RuntimeError(
        f"Impossible de récupérer les données "
        f"{symbol} {timeframe}: {last_error}"
    )


def get_latest_price(symbol: str) -> float:

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