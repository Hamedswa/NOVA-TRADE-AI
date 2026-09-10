"""
NOVA TRADE AI
Moteur 2 - Client BiQuote

Responsabilités :
- récupérer les ticks BiQuote lorsqu'ils sont disponibles ;
- récupérer les chandeliers OHLC ;
- normaliser les données ;
- vérifier la cohérence des données ;
- vérifier la fraîcheur lorsqu'elle est fournie ;
- ne contenir aucune logique de trading.

Actifs Moteur 2 :
    XAUUSD
    BTCUSD
    EURUSD
    GBPUSD

Timeframes :
    H4
    H1
    M15
    M5
    M1

IMPORTANT :
Le prix temps réel privilégié du Moteur 2 provient du
flux BiQuote SignalR via biquote_stream.py.

Ce client REST ne décide jamais :
    - BUY / SELL
    - Entry
    - SL
    - TP
    - RR
    - score
    - validation
    - rejet de signal
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

DEFAULT_TIMEOUT = 10

MAX_RETRIES = 3


# ============================================================
# ACTIFS SUPPORTÉS
# ============================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)


# ============================================================
# TIMEFRAMES SUPPORTÉS
# ============================================================

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
    """
    Tick normalisé BiQuote.

    Le tick est une donnée de marché uniquement.
    Aucune décision de trading n'est prise ici.
    """

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
    """
    Bougie OHLC normalisée.
    """

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

    Elle ne contient aucune logique :
        - de setup ;
        - de signal ;
        - de score ;
        - de risque ;
        - de validation ;
        - d'exécution.
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
    # NORMALISATION SYMBOLE
    # ========================================================

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """
        Normalise un symbole vers le format interne BiQuote.

        Exemples :
            XAU/USD -> XAUUSD
            BTC/USD -> BTCUSD
            EUR/USD -> EURUSD
            GBP/USD -> GBPUSD
        """

        if not isinstance(symbol, str):
            raise ValueError(
                "Le symbole doit être une chaîne."
            )

        normalized = (
            symbol.strip()
            .upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
        )

        if normalized not in SUPPORTED_SYMBOLS:
            raise ValueError(
                f"Symbole BiQuote non supporté : {symbol}. "
                f"Symboles autorisés : "
                f"{', '.join(SUPPORTED_SYMBOLS)}"
            )

        return normalized

    # ========================================================
    # VALIDATION TIMEFRAME
    # ========================================================

    @staticmethod
    def normalize_timeframe(timeframe: str) -> str:
        """
        Normalise et vérifie un timeframe.
        """

        if not isinstance(timeframe, str):
            raise ValueError(
                "Le timeframe doit être une chaîne."
            )

        normalized = timeframe.strip().upper()

        if normalized not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Timeframe BiQuote non supporté : "
                f"{timeframe}. "
                f"Timeframes autorisés : "
                f"{', '.join(SUPPORTED_TIMEFRAMES)}"
            )

        return normalized

    # ========================================================
    # HTTP
    # ========================================================

    def _get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """
        Effectue une requête GET avec quelques protections
        réseau basiques.
        """

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

                # ------------------------------------------------
                # RATE LIMIT
                # ------------------------------------------------

                if response.status_code == 429:

                    retry_after_raw = (
                        response.headers.get(
                            "Retry-After",
                            "2",
                        )
                    )

                    try:
                        retry_after = max(
                            1,
                            int(retry_after_raw),
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        retry_after = 2

                    logger.warning(
                        "BiQuote rate limit "
                        "(tentative %s/%s). "
                        "Attente de %ss.",
                        attempt,
                        self.max_retries,
                        retry_after,
                    )

                    time.sleep(
                        retry_after
                    )

                    continue

                # ------------------------------------------------
                # ERREUR HTTP
                # ------------------------------------------------

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

                # ------------------------------------------------
                # JSON
                # ------------------------------------------------

                try:

                    return response.json()

                except ValueError as exc:

                    raise BiQuoteDataError(
                        "BiQuote a retourné une réponse "
                        "qui n'est pas un JSON valide."
                    ) from exc

            except BiQuoteHTTPError:
                raise

            except BiQuoteDataError:
                raise

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

                    time.sleep(attempt)

        raise BiQuoteError(
            "Impossible de contacter BiQuote "
            f"après {self.max_retries} tentatives."
        ) from last_error

    # ========================================================
    # TICK
    # ========================================================

    def get_tick(
        self,
        symbol: str,
        allow_stale: bool = False,
    ) -> Tick:
        """
        Récupère un tick REST BiQuote.

        IMPORTANT :
        Le flux SignalR de biquote_stream.py reste la source
        privilégiée pour le prix temps réel du Moteur 2.

        Cette méthode ne contient aucune logique de trading.
        """

        symbol = self.normalize_symbol(symbol)

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

            bid = float(
                payload["bid"]
            )

            ask = float(
                payload["ask"]
            )

            mid = float(
                payload["mid"]
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
                f"Tick BiQuote incomplet ou "
                f"invalide pour {symbol}."
            ) from exc

        # ----------------------------------------------------
        # VALIDATION PRIX
        # ----------------------------------------------------

        if bid <= 0:
            raise BiQuoteDataError(
                f"Bid invalide pour {symbol}: {bid}"
            )

        if ask <= 0:
            raise BiQuoteDataError(
                f"Ask invalide pour {symbol}: {ask}"
            )

        if mid <= 0:
            raise BiQuoteDataError(
                f"Mid invalide pour {symbol}: {mid}"
            )

        if ask < bid:
            raise BiQuoteDataError(
                f"Ask inférieur au bid pour {symbol}: "
                f"bid={bid}, ask={ask}"
            )

        if spread < 0:
            raise BiQuoteDataError(
                f"Spread négatif pour {symbol}: {spread}"
            )

        # ----------------------------------------------------
        # SYMBOLE RETOURNÉ
        # ----------------------------------------------------

        payload_symbol = str(
            payload.get(
                "symbol",
                symbol,
            )
        )

        try:

            normalized_payload_symbol = (
                self.normalize_symbol(
                    payload_symbol
                )
            )

        except ValueError:

            normalized_payload_symbol = symbol

        # ----------------------------------------------------
        # ÂGE DE LA COTE
        # ----------------------------------------------------

        raw_age = payload.get(
            "quoteAgeSeconds",
            0,
        )

        try:

            quote_age_seconds = float(
                raw_age or 0
            )

        except (
            TypeError,
            ValueError,
        ):

            quote_age_seconds = 0.0

        quote_age_seconds = max(
            0.0,
            quote_age_seconds,
        )

        # ----------------------------------------------------
        # ÉTAT DU MARCHÉ
        # ----------------------------------------------------

        market_state = str(
            payload.get(
                "marketState",
                "unknown",
            )
        )

        stale = bool(
            payload.get(
                "stale",
                False,
            )
        )

        direction = str(
            payload.get(
                "direction",
                "FLAT",
            )
        ).upper()

        return Tick(
            symbol=normalized_payload_symbol,
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
            market_state=market_state,
            stale=stale,
            quote_age_seconds=quote_age_seconds,
            direction=direction,
        )

    # ========================================================
    # OHLC
    # ========================================================

    def get_candles(
        self,
        timeframe: str,
        symbol: str,
        limit: int = 500,
        closed_only: bool = False,
    ) -> list[Candle]:
        """
        Récupère les chandeliers OHLC BiQuote.

        Les données restent strictement isolées par :
            symbole
            timeframe
        """

        symbol = self.normalize_symbol(symbol)

        timeframe = self.normalize_timeframe(
            timeframe
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
                    "Bougie BiQuote ignorée "
                    "pour %s %s : %s",
                    symbol,
                    timeframe,
                    bar,
                )

                continue

            # ------------------------------------------------
            # VALIDATION OHLC
            # ------------------------------------------------

            if candle.open <= 0:
                logger.warning(
                    "Open invalide ignoré : %s",
                    candle,
                )
                continue

            if candle.high <= 0:
                logger.warning(
                    "High invalide ignoré : %s",
                    candle,
                )
                continue

            if candle.low <= 0:
                logger.warning(
                    "Low invalide ignoré : %s",
                    candle,
                )
                continue

            if candle.close <= 0:
                logger.warning(
                    "Close invalide ignoré : %s",
                    candle,
                )
                continue

            if candle.high < candle.low:

                logger.warning(
                    "Bougie incohérente ignorée : %s",
                    candle,
                )

                continue

            if not (
                candle.low
                <= candle.open
                <= candle.high
            ):

                logger.warning(
                    "Open incohérent ignoré : %s",
                    candle,
                )

                continue

            if not (
                candle.low
                <= candle.close
                <= candle.high
            ):

                logger.warning(
                    "Close incohérent ignoré : %s",
                    candle,
                )

                continue

            # ------------------------------------------------
            # BOUGIE OUVERTE
            # ------------------------------------------------

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

        # ----------------------------------------------------
        # TRI CHRONOLOGIQUE
        # ----------------------------------------------------

        candles.sort(
            key=lambda candle: candle.open_time
        )

        return candles

    # ========================================================
    # ALIAS OHLC
    # ========================================================

    def get_ohlc(
        self,
        timeframe: str,
        symbol: str,
        limit: int = 500,
        closed_only: bool = False,
    ) -> list[Candle]:
        """
        Alias de compatibilité pour get_candles().

        Aucune logique supplémentaire.
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
        symbol: str,
        limit: int = 500,
        closed_only: bool = True,
    ) -> dict[str, list[Candle]]:
        """
        Récupère les cinq timeframes du Moteur 2
        pour un seul symbole.

        Important :
        une invocation concerne un seul symbole afin d'éviter
        tout mélange de données entre actifs.
        """

        symbol = self.normalize_symbol(symbol)

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
    # TOUS LES ACTIFS
    # ========================================================

    def get_all_symbols_timeframes(
        self,
        limit: int = 500,
        closed_only: bool = True,
    ) -> dict[
        str,
        dict[str, list[Candle]],
    ]:
        """
        Récupère les cinq timeframes pour chacun des quatre
        actifs du Moteur 2.

        Structure retournée :

        {
            "XAUUSD": {
                "H4": [...],
                "H1": [...],
                "M15": [...],
                "M5": [...],
                "M1": [...],
            },
            "BTCUSD": {...},
            "EURUSD": {...},
            "GBPUSD": {...},
        }

        Cette méthode ne fait aucun calcul de trading.
        """

        result: dict[
            str,
            dict[str, list[Candle]],
        ] = {}

        for symbol in SUPPORTED_SYMBOLS:

            result[symbol] = self.get_all_timeframes(
                symbol=symbol,
                limit=limit,
                closed_only=closed_only,
            )

        return result

    # ========================================================
    # FERMETURE SESSION HTTP
    # ========================================================

    def close(self) -> None:
        """
        Ferme proprement la session HTTP.
        """

        self.session.close()


# ============================================================
# INSTANCE SIMPLE
# ============================================================

biquote = BiQuoteClient()