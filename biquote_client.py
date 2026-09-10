"""
NOVA TRADE AI
Moteur 2 - Client BiQuote

Responsabilités :
- récupérer les ticks XAUUSD ;
- récupérer les chandeliers OHLC ;
- normaliser les données ;
- vérifier la fraîcheur des données ;
- ne contenir aucune logique de trading.

Source :
BiQuote
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests


logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://biquote.io"

SYMBOL = "XAUUSD"

DEFAULT_TIMEOUT = 10

MAX_RETRIES = 3

SUPPORTED_TIMEFRAMES = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "H1": "1h",
    "H4": "4h",
}


# ============================================================
# EXCEPTIONS
# ============================================================

class BiQuoteError(Exception):
    """Erreur générale BiQuote."""


class BiQuoteHTTPError(BiQuoteError):
    """Erreur HTTP provenant de BiQuote."""


class BiQuoteDataError(BiQuoteError):
    """Données BiQuote invalides ou incomplètes."""


# ============================================================
# MODÈLES DE DONNÉES
# ============================================================

@dataclass(frozen=True)
class Tick:
    """Tick normalisé BiQuote."""

    symbol: str
    bid: float
    ask: float
    mid: float
    spread: float

    timestamp: str

    market_state: str
    stale: bool
    quote_age_seconds: float

    direction: str = "FLAT"


@dataclass(frozen=True)
class Candle:
    """Bougie OHLC normalisée."""

    open_time: str

    open: float
    high: float
    low: float
    close: float

    tick_volume: int

    is_open: bool


# ============================================================
# CLIENT
# ============================================================

class BiQuoteClient:
    """
    Client REST minimal pour le Moteur 2.

    Cette classe fournit uniquement les données BiQuote.

    Elle ne contient aucune logique de trading.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:

        self.base_url = base_url.rstrip("/")

        self.timeout = timeout

        self.max_retries = max_retries

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": "NOVA-TRADE-AI-MOTOR-2/1.0",
                "Accept": "application/json",
            }
        )

    # ========================================================
    # HTTP
    # ========================================================

    def _get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:

        url = f"{self.base_url}{endpoint}"

        last_error: Optional[Exception] = None

        for attempt in range(
            1,
            self.max_retries + 1,
        ):

            try:

                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )

                if response.status_code == 429:

                    retry_after = int(
                        response.headers.get(
                            "Retry-After",
                            "2",
                        )
                    )

                    logger.warning(
                        "BiQuote rate limit. "
                        "Attente de %ss.",
                        retry_after,
                    )

                    time.sleep(
                        retry_after
                    )

                    continue

                if response.status_code >= 400:

                    try:
                        payload = response.json()

                    except Exception:
                        payload = response.text

                    raise BiQuoteHTTPError(
                        f"BiQuote HTTP "
                        f"{response.status_code}: "
                        f"{payload}"
                    )

                return response.json()

            except requests.RequestException as exc:

                last_error = exc

                logger.warning(
                    "Erreur réseau BiQuote "
                    "(tentative %s/%s): %s",
                    attempt,
                    self.max_retries,
                    exc,
                )

                if attempt < self.max_retries:

                    time.sleep(
                        attempt
                    )

        raise BiQuoteError(
            "Impossible de contacter BiQuote "
            f"après {self.max_retries} tentatives."
        ) from last_error

    # ========================================================
    # TICK
    # ========================================================

    def get_tick(
        self,
        symbol: str = SYMBOL,
        allow_stale: bool = False,
    ) -> Tick:

        symbol = symbol.upper()

        if symbol != SYMBOL:
            raise ValueError(
                "Le Moteur 2 BiQuote est limité à XAUUSD."
            )

        payload = self._get(
            f"/api/{symbol}",
            params={
                "allowStale": str(
                    allow_stale
                ).lower(),
            },
        )

        if not isinstance(
            payload,
            dict,
        ):

            raise BiQuoteDataError(
                "Réponse tick BiQuote invalide."
            )

        try:

            mid = float(
                payload["mid"]
            )

            bid = float(
                payload["bid"]
            )

            ask = float(
                payload["ask"]
            )

            spread = float(
                payload["spread"]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:

            raise BiQuoteDataError(
                "Tick BiQuote incomplet ou invalide."
            ) from exc

        if mid <= 0:

            raise BiQuoteDataError(
                f"Prix mid invalide pour "
                f"{symbol}: {mid}"
            )

        return Tick(
            symbol=str(
                payload.get(
                    "symbol",
                    symbol,
                )
            ),
            bid=bid,
            ask=ask,
            mid=mid,
            spread=spread,
            timestamp=str(
                payload.get(
                    "timestamp",
                    "",
                )
            ),
            market_state=str(
                payload.get(
                    "marketState",
                    "unknown",
                )
            ),
            stale=bool(
                payload.get(
                    "stale",
                    False,
                )
            ),
            quote_age_seconds=float(
                payload.get(
                    "quoteAgeSeconds",
                    0,
                )
                or 0
            ),
            direction=str(
                payload.get(
                    "direction",
                    "FLAT",
                )
            ),
        )

    # ========================================================
    # OHLC
    # ========================================================

    def get_candles(
        self,
        timeframe: str,
        symbol: str = SYMBOL,
        limit: int = 500,
        closed_only: bool = False,
    ) -> list[Candle]:

        timeframe = timeframe.upper()

        symbol = symbol.upper()

        if symbol != SYMBOL:

            raise ValueError(
                "Le Moteur 2 BiQuote est limité à XAUUSD."
            )

        if timeframe not in SUPPORTED_TIMEFRAMES:

            raise ValueError(
                f"Timeframe non supporté: {timeframe}. "
                f"Utiliser: "
                f"{', '.join(SUPPORTED_TIMEFRAMES)}"
            )

        if not 1 <= limit <= 1000:

            raise ValueError(
                "limit doit être compris "
                "entre 1 et 1000."
            )

        interval = SUPPORTED_TIMEFRAMES[
            timeframe
        ]

        payload = self._get(
            f"/api/{symbol}/ohlc",
            params={
                "interval": interval,
                "limit": limit,
            },
        )

        if not isinstance(
            payload,
            dict,
        ):

            raise BiQuoteDataError(
                "Réponse OHLC BiQuote invalide."
            )

        bars = payload.get(
            "bars"
        )

        if not isinstance(
            bars,
            list,
        ):

            raise BiQuoteDataError(
                "Champ 'bars' absent ou invalide."
            )

        candles: list[Candle] = []

        for bar in bars:

            if not isinstance(
                bar,
                dict,
            ):
                continue

            try:

                candle = Candle(
                    open_time=str(
                        bar["openTime"]
                    ),
                    open=float(
                        bar["open"]
                    ),
                    high=float(
                        bar["high"]
                    ),
                    low=float(
                        bar["low"]
                    ),
                    close=float(
                        bar["close"]
                    ),
                    tick_volume=int(
                        bar.get(
                            "tickVolume",
                            0,
                        )
                        or 0
                    ),
                    is_open=bool(
                        bar.get(
                            "isOpen",
                            False,
                        )
                    ),
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                logger.warning(
                    "Bougie BiQuote ignorée: %s",
                    bar,
                )

                continue

            if candle.high < candle.low:

                logger.warning(
                    "Bougie incohérente ignorée: %s",
                    candle,
                )

                continue

            if not (
                candle.low
                <= candle.open
                <= candle.high
            ):

                logger.warning(
                    "Open incohérent ignoré: %s",
                    candle,
                )

                continue

            if not (
                candle.low
                <= candle.close
                <= candle.high
            ):

                logger.warning(
                    "Close incohérent ignoré: %s",
                    candle,
                )

                continue

            if (
                closed_only
                and candle.is_open
            ):

                continue

            candles.append(
                candle
            )

        if not candles:

            raise BiQuoteDataError(
                f"Aucune bougie valide reçue "
                f"pour {symbol} {timeframe}."
            )

        candles.sort(
            key=lambda candle: candle.open_time
        )

        return candles

    # ========================================================
    # COMPATIBILITÉ MOTEUR 2
    # ========================================================

    def get_ohlc(
        self,
        timeframe: str,
        symbol: str = SYMBOL,
        limit: int = 500,
        closed_only: bool = False,
    ) -> list[Candle]:
        """
        Alias de compatibilité pour le Moteur 2.

        Le client BiQuote officiel du projet utilise
        get_candles(). Cette méthode permet aux anciennes
        parties du Moteur 2 qui appellent encore get_ohlc()
        de fonctionner sans dupliquer la logique OHLC.

        Aucun calcul de trading n'est effectué ici.
        """

        return self.get_candles(
            timeframe=timeframe,
            symbol=symbol,
            limit=limit,
            closed_only=closed_only,
        )

    # ========================================================
    # TOUS LES TIMEFRAMES
    # ========================================================

    def get_all_timeframes(
        self,
        symbol: str = SYMBOL,
        limit: int = 500,
        closed_only: bool = True,
    ) -> dict[str, list[Candle]]:

        symbol = symbol.upper()

        if symbol != SYMBOL:

            raise ValueError(
                "Le Moteur 2 BiQuote est limité à XAUUSD."
            )

        data: dict[
            str,
            list[Candle],
        ] = {}

        for timeframe in (
            "H4",
            "H1",
            "M15",
            "M5",
            "M1",
        ):

            data[timeframe] = self.get_candles(
                timeframe=timeframe,
                symbol=symbol,
                limit=limit,
                closed_only=closed_only,
            )

        return data

    # ========================================================
    # FERMETURE
    # ========================================================

    def close(self) -> None:

        self.session.close()


# ============================================================
# INSTANCE SIMPLE
# ============================================================

biquote = BiQuoteClient()