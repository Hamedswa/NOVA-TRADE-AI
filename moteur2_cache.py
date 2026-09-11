"""
NOVA TRADE AI - Moteur 2
moteur2_cache.py

Cache centralisé des données BiQuote pour le Moteur 2.

Actif principal :
    XAUUSD

Timeframes :
    H4
    H1
    M15
    M5
    M1

Architecture :
    BiQuote REST
         |
         v
    bougies clôturées
         |
         v
    Moteur2Cache
         ^
         |
    BiQuote SignalR
         |
         v
    ticks temps réel

Important :
    - BiQuote est la seule source du Moteur 2.
    - Les ticks SignalR servent au prix temps réel.
    - Un tick temps réel n'est jamais transformé en bougie.
    - Les bougies d'analyse sont récupérées séparément.
    - Le cache est isolé par symbole.
    - Ce module ne contient aucune logique de trading.
"""

from __future__ import annotations

import asyncio
import logging
import time

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from biquote_client import (
    BiQuoteClient,
    Candle,
    Tick,
)


logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)

SUPPORTED_TIMEFRAMES = (
    "H4",
    "H1",
    "M15",
    "M5",
    "M1",
)


TIMEFRAME_REFRESH_SECONDS = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 10 * 60,
    "M1": 60,
}


DEFAULT_LIMIT = {
    "H4": 300,
    "H1": 500,
    "M15": 500,
    "M5": 500,
    "M1": 500,
}


# ============================================================================
# STRUCTURES INTERNES
# ============================================================================

@dataclass
class TimeframeCache:
    """
    État du cache d'un timeframe pour un symbole.
    """

    timeframe: str
    candles: List[Candle]
    last_refresh: float = 0.0
    refreshing: bool = False
    error: Optional[str] = None


# ============================================================================
# CACHE PRINCIPAL
# ============================================================================

class Moteur2Cache:
    """
    Cache centralisé des données BiQuote du Moteur 2.

    Compatibilité :

        Moteur2Cache(
            client=client,
            symbol="XAUUSD",
        )

    ou :

        Moteur2Cache(
            client=client,
            symbols=["XAUUSD"],
        )

    Le paramètre symbol permet au Moteur 2
    de fonctionner avec un seul actif.
    """

    def __init__(
        self,
        client: Optional[BiQuoteClient] = None,
        symbol: Optional[str] = None,
        symbols: Optional[
            list[str] | tuple[str, ...]
        ] = None,
    ):
        self.client = client or BiQuoteClient()

        # ------------------------------------------------------------------
        # Compatibilité avec moteur2.py
        # ------------------------------------------------------------------

        if symbol is not None:
            symbols = [symbol]

        # ------------------------------------------------------------------
        # Symboles
        # ------------------------------------------------------------------

        if symbols is None:
            symbols = SUPPORTED_SYMBOLS

        normalized_symbols: List[str] = []

        for symbol_value in symbols:

            normalized = self._normalize_symbol(
                symbol_value
            )

            if not normalized:
                continue

            if normalized not in SUPPORTED_SYMBOLS:
                logger.warning(
                    "Symbole ignoré dans le cache : %s",
                    symbol_value,
                )
                continue

            if normalized not in normalized_symbols:
                normalized_symbols.append(
                    normalized
                )

        if not normalized_symbols:
            raise ValueError(
                "Aucun symbole valide pour Moteur2Cache."
            )

        self.symbols = tuple(
            normalized_symbols
        )

        # ------------------------------------------------------------------
        # Cache des bougies
        # ------------------------------------------------------------------

        self._cache: Dict[
            str,
            Dict[str, TimeframeCache],
        ] = {
            symbol_value: {
                timeframe: TimeframeCache(
                    timeframe=timeframe,
                    candles=[],
                )
                for timeframe in SUPPORTED_TIMEFRAMES
            }
            for symbol_value in self.symbols
        }

        # ------------------------------------------------------------------
        # Dernier tick par symbole
        # ------------------------------------------------------------------

        self._latest_ticks: Dict[
            str,
            Tick,
        ] = {}

        # ------------------------------------------------------------------
        # Locks
        # ------------------------------------------------------------------

        self._locks: Dict[
            str,
            Dict[str, asyncio.Lock],
        ] = {
            symbol_value: {
                timeframe: asyncio.Lock()
                for timeframe in SUPPORTED_TIMEFRAMES
            }
            for symbol_value in self.symbols
        }

    # =========================================================================
    # SYMBOL HELPERS
    # =========================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:

        if not isinstance(symbol, str):
            return ""

        return (
            symbol.upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .replace(" ", "")
            .strip()
        )

    def _validate_symbol(
        self,
        symbol: str,
    ) -> str:

        normalized = self._normalize_symbol(
            symbol
        )

        if normalized not in self.symbols:
            raise ValueError(
                f"Symbole non disponible dans le cache : "
                f"{symbol}"
            )

        return normalized

    @staticmethod
    def _validate_timeframe(
        timeframe: str,
    ) -> str:

        normalized = str(
            timeframe
        ).upper()

        if normalized not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Timeframe non supporté : "
                f"{timeframe}"
            )

        return normalized

    # =========================================================================
    # TICK TEMPS RÉEL
    # =========================================================================

    def update_tick(
        self,
        tick: Any,
    ) -> None:

        try:

            normalized = self._normalize_tick(
                tick
            )

            if normalized is None:
                return

            symbol = self._normalize_symbol(
                normalized.symbol
            )

            if symbol not in self.symbols:
                logger.debug(
                    "Tick ignoré : symbole non configuré %s",
                    symbol,
                )
                return

            self._latest_ticks[
                symbol
            ] = normalized

        except Exception:
            logger.exception(
                "Erreur mise à jour tick Moteur 2."
            )

    def get_latest_tick(
        self,
        symbol: Optional[str] = None,
    ) -> Optional[Tick]:
        """
        Retourne le dernier tick connu.

        Si symbol est absent et qu'un seul symbole
        est configuré, ce symbole est utilisé.
        """

        if symbol is None:

            if len(self.symbols) != 1:
                raise ValueError(
                    "Le symbole doit être précisé lorsque "
                    "plusieurs symboles sont configurés."
                )

            symbol = self.symbols[0]

        normalized = self._validate_symbol(
            symbol
        )

        return self._latest_ticks.get(
            normalized
        )

    def get_current_price(
        self,
        symbol: Optional[str] = None,
    ) -> Optional[float]:
        """
        Retourne le dernier prix mid connu.

        Compatibilité :

            get_current_price()

        lorsque le cache ne contient qu'un seul symbole.

        Ou :

            get_current_price("XAUUSD")
        """

        tick = self.get_latest_tick(
            symbol
        )

        if tick is None:
            return None

        return tick.mid

    def get_latest_ticks(
        self,
    ) -> Dict[str, Tick]:

        return dict(
            self._latest_ticks
        )

    # =========================================================================
    # BOUGIES
    # =========================================================================

    async def refresh(
        self,
        symbol: str,
        timeframe: str,
        force: bool = False,
    ) -> List[Candle]:

        symbol = self._validate_symbol(
            symbol
        )

        timeframe = self._validate_timeframe(
            timeframe
        )

        cache = self._cache[
            symbol
        ][
            timeframe
        ]

        if (
            not force
            and not self._needs_refresh(
                symbol,
                timeframe,
            )
        ):
            return list(
                cache.candles
            )

        lock = self._locks[
            symbol
        ][
            timeframe
        ]

        async with lock:

            if (
                not force
                and not self._needs_refresh(
                    symbol,
                    timeframe,
                )
            ):
                return list(
                    cache.candles
                )

            cache.refreshing = True
            cache.error = None

            try:

                logger.info(
                    "Moteur 2 | récupération %s %s",
                    symbol,
                    timeframe,
                )

                candles = await asyncio.to_thread(
                    self.client.get_candles,
                    timeframe,
                    symbol,
                    DEFAULT_LIMIT[timeframe],
                    True,
                )

                if not candles:
                    raise RuntimeError(
                        f"Aucune bougie reçue pour "
                        f"{symbol} {timeframe}"
                    )

                valid_candles = [
                    candle
                    for candle in candles
                    if isinstance(
                        candle,
                        Candle,
                    )
                ]

                if not valid_candles:
                    raise RuntimeError(
                        f"Aucune bougie Candle valide "
                        f"pour {symbol} {timeframe}"
                    )

                cache.candles = list(
                    valid_candles
                )

                cache.last_refresh = time.time()
                cache.error = None

                logger.info(
                    "Moteur 2 | %s %s : %d bougies chargées",
                    symbol,
                    timeframe,
                    len(cache.candles),
                )

                return list(
                    cache.candles
                )

            except Exception as exc:

                cache.error = str(
                    exc
                )

                logger.exception(
                    "Erreur récupération %s %s",
                    symbol,
                    timeframe,
                )

                if cache.candles:
                    return list(
                        cache.candles
                    )

                raise

            finally:

                cache.refreshing = False

    async def refresh_symbol(
        self,
        symbol: str,
        force: bool = False,
    ) -> Dict[str, List[Candle]]:

        symbol = self._validate_symbol(
            symbol
        )

        results = await asyncio.gather(
            *[
                self.refresh(
                    symbol,
                    timeframe,
                    force=force,
                )
                for timeframe in SUPPORTED_TIMEFRAMES
            ],
            return_exceptions=True,
        )

        output: Dict[
            str,
            List[Candle],
        ] = {}

        for timeframe, result in zip(
            SUPPORTED_TIMEFRAMES,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):

                logger.error(
                    "Refresh %s %s échoué : %s",
                    symbol,
                    timeframe,
                    result,
                )

                output[timeframe] = []

            else:

                output[timeframe] = list(
                    result
                )

        return output

    async def refresh_all(
        self,
        force: bool = False,
    ) -> Dict[
        str,
        Dict[str, List[Candle]],
    ]:

        results = await asyncio.gather(
            *[
                self.refresh_symbol(
                    symbol,
                    force=force,
                )
                for symbol in self.symbols
            ],
            return_exceptions=True,
        )

        output: Dict[
            str,
            Dict[str, List[Candle]],
        ] = {}

        for symbol, result in zip(
            self.symbols,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):

                logger.error(
                    "Refresh global %s échoué : %s",
                    symbol,
                    result,
                )

                output[symbol] = {
                    timeframe: []
                    for timeframe
                    in SUPPORTED_TIMEFRAMES
                }

            else:

                output[symbol] = result

        return output

    # =========================================================================
    # ACCÈS AUX BOUGIES
    # =========================================================================

    def get_candles(
        self,
        symbol_or_timeframe: str,
        timeframe: Optional[str] = None,
    ) -> List[Candle]:
        """
        Compatibilité avec deux formes :

            get_candles("XAUUSD", "H1")

        ou, pour un cache mono-symbole :

            get_candles("H1")
        """

        if timeframe is None:

            if len(self.symbols) != 1:
                raise ValueError(
                    "Le symbole doit être précisé lorsque "
                    "plusieurs symboles sont configurés."
                )

            symbol = self.symbols[0]
            timeframe = symbol_or_timeframe

        else:

            symbol = symbol_or_timeframe

        symbol = self._validate_symbol(
            symbol
        )

        timeframe = self._validate_timeframe(
            timeframe
        )

        return list(
            self._cache[
                symbol
            ][
                timeframe
            ].candles
        )

    def get_closed_candles(
        self,
        symbol_or_timeframe: str,
        timeframe: Optional[str] = None,
    ) -> List[Candle]:
        """
        Compatibilité avec deux formes :

            get_closed_candles("XAUUSD", "H1")

        ou, pour un cache mono-symbole :

            get_closed_candles("H1")
        """

        if timeframe is None:

            if len(self.symbols) != 1:
                raise ValueError(
                    "Le symbole doit être précisé lorsque "
                    "plusieurs symboles sont configurés."
                )

            symbol = self.symbols[0]
            timeframe = symbol_or_timeframe

        else:

            symbol = symbol_or_timeframe

        candles = self.get_candles(
            symbol,
            timeframe,
        )

        return [
            candle
            for candle in candles
            if self._is_closed_candle(
                candle
            )
        ]

    def get_latest_closed_candle(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> Optional[Candle]:
        """
        Retourne la dernière bougie clôturée.

        Compatibilité :

            get_latest_closed_candle("XAUUSD", "H1")

        ou :

            get_latest_closed_candle("H1")
        """

        if timeframe is None:

            if symbol is None:
                raise ValueError(
                    "Le timeframe doit être précisé."
                )

            timeframe = symbol
            symbol = None

        candles = self.get_closed_candles(
            symbol if symbol is not None
            else timeframe,
            timeframe if symbol is not None
            else None,
        )

        if not candles:
            return None

        return candles[-1]

    def get_symbol_data(
        self,
        symbol: Optional[str] = None,
    ) -> Dict[
        str,
        List[Candle],
    ]:

        if symbol is None:

            if len(self.symbols) != 1:
                raise ValueError(
                    "Le symbole doit être précisé lorsque "
                    "plusieurs symboles sont configurés."
                )

            symbol = self.symbols[0]

        symbol = self._validate_symbol(
            symbol
        )

        return {
            timeframe: list(
                self._cache[
                    symbol
                ][
                    timeframe
                ].candles
            )
            for timeframe
            in SUPPORTED_TIMEFRAMES
        }

    # =========================================================================
    # REFRESH STATE
    # =========================================================================

    def needs_refresh(
        self,
        symbol: str,
        timeframe: str,
    ) -> bool:

        symbol = self._validate_symbol(
            symbol
        )

        timeframe = self._validate_timeframe(
            timeframe
        )

        return self._needs_refresh(
            symbol,
            timeframe,
        )

    def _needs_refresh(
        self,
        symbol: str,
        timeframe: str,
    ) -> bool:

        cache = self._cache[
            symbol
        ][
            timeframe
        ]

        if not cache.candles:
            return True

        if cache.last_refresh <= 0:
            return True

        elapsed = (
            time.time()
            - cache.last_refresh
        )

        return (
            elapsed
            >= TIMEFRAME_REFRESH_SECONDS[
                timeframe
            ]
        )

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(
        self,
    ) -> Dict[str, Any]:

        now = time.time()

        status: Dict[
            str,
            Any,
        ] = {
            "provider": "BiQuote",
            "symbols": list(
                self.symbols
            ),
            "symbol_count": len(
                self.symbols
            ),
            "timeframes": list(
                SUPPORTED_TIMEFRAMES
            ),
            "latest_ticks": {},
            "markets": {},
        }

        for symbol in self.symbols:

            tick = self._latest_ticks.get(
                symbol
            )

            if tick is None:

                status[
                    "latest_ticks"
                ][symbol] = {
                    "received": False,
                    "price": None,
                }

            else:

                status[
                    "latest_ticks"
                ][symbol] = {
                    "received": True,
                    "price": tick.mid,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "spread": tick.spread,
                    "timestamp": tick.timestamp,
                    "market_state": tick.market_state,
                    "stale": tick.stale,
                    "quote_age_seconds": (
                        tick.quote_age_seconds
                    ),
                }

        for symbol in self.symbols:

            status[
                "markets"
            ][symbol] = {
                "current_price": (
                    self.get_current_price(
                        symbol
                    )
                ),
                "timeframes": {},
            }

            for timeframe in SUPPORTED_TIMEFRAMES:

                cache = self._cache[
                    symbol
                ][
                    timeframe
                ]

                age = None

                if cache.last_refresh > 0:

                    age = round(
                        now
                        - cache.last_refresh,
                        2,
                    )

                status[
                    "markets"
                ][symbol][
                    "timeframes"
                ][timeframe] = {

                    "candles": len(
                        cache.candles
                    ),

                    "last_refresh_age": age,

                    "needs_refresh": (
                        self._needs_refresh(
                            symbol,
                            timeframe,
                        )
                    ),

                    "refreshing": (
                        cache.refreshing
                    ),

                    "error": cache.error,
                }

        return status

    # =========================================================================
    # TICK NORMALIZATION
    # =========================================================================

    def _normalize_tick(
        self,
        tick: Any,
    ) -> Optional[Tick]:

        if isinstance(
            tick,
            Tick,
        ):
            return tick

        if not isinstance(
            tick,
            dict,
        ):
            return None

        symbol = self._normalize_symbol(
            tick.get(
                "symbol",
                "",
            )
        )

        if not symbol:
            return None

        mid = self._safe_float(
            tick.get("mid")
        )

        if mid is None or mid <= 0:
            return None

        bid = self._safe_float(
            tick.get("bid")
        )

        ask = self._safe_float(
            tick.get("ask")
        )

        spread = self._safe_float(
            tick.get("spread")
        )

        return Tick(
            symbol=symbol,
            bid=bid,
            ask=ask,
            mid=mid,
            spread=spread,
            timestamp=tick.get(
                "timestamp"
            ),
            market_state=tick.get(
                "marketState"
            ),
            stale=tick.get(
                "stale"
            ),
            quote_age_seconds=(
                self._safe_float(
                    tick.get(
                        "quoteAgeSeconds"
                    )
                )
            ),
        )

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _is_closed_candle(
        candle: Candle,
    ) -> bool:

        return not bool(
            getattr(
                candle,
                "is_open",
                False,
            )
        )


# ============================================================================
# TEST LOCAL
# ============================================================================

async def main() -> None:

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
    )

    cache = Moteur2Cache()

    print()
    print("=" * 70)
    print(
        "NOVA TRADE AI - TEST MOTEUR 2 CACHE"
    )
    print("=" * 70)
    print()

    for symbol in cache.symbols:

        print(
            f"--- {symbol} H1 ---"
        )

        try:

            await cache.refresh(
                symbol,
                "H1",
                force=True,
            )

            candles = (
                cache.get_closed_candles(
                    symbol,
                    "H1",
                )
            )

            print(
                f"{symbol} H1 : "
                f"{len(candles)} "
                f"bougies clôturées"
            )

            latest = (
                cache.get_latest_closed_candle(
                    symbol,
                    "H1",
                )
            )

            if latest is not None:

                print(
                    f"Open  : {latest.open}"
                )

                print(
                    f"High  : {latest.high}"
                )

                print(
                    f"Low   : {latest.low}"
                )

                print(
                    f"Close : {latest.close}"
                )

            print()

        except Exception as exc:

            print(
                f"Erreur {symbol} H1 : {exc}"
            )

    print()
    print("=" * 70)
    print("ÉTAT DU CACHE")
    print("=" * 70)
    print()

    status = cache.get_status()

    print(
        status
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )