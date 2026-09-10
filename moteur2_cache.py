"""
NOVA TRADE AI - Moteur 2
moteur2_cache.py

Gestion centralisée du cache de données BiQuote pour XAU/USD.

Timeframes :
    H4  -> rafraîchissement toutes les 8 heures
    H1  -> rafraîchissement toutes les 2 heures
    M15 -> rafraîchissement toutes les 30 minutes
    M5  -> rafraîchissement toutes les 10 minutes
    M1  -> rafraîchissement toutes les 1 minute

Important :
    - BiQuote est la seule source du Moteur 2.
    - Les ticks SignalR mettent à jour le prix temps réel.
    - Un tick temps réel n'est PAS considéré comme une bougie M1 clôturée.
    - Les bougies utilisées pour l'analyse peuvent être limitées
      aux bougies clôturées.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from biquote_client import BiQuoteClient, Candle, Tick


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOL = "XAUUSD"

TIMEFRAME_REFRESH_SECONDS = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 10 * 60,
    "M1": 60,
}

# Nombre de bougies conservées par timeframe.
DEFAULT_LIMIT = {
    "H4": 300,
    "H1": 500,
    "M15": 500,
    "M5": 500,
    "M1": 500,
}


# ---------------------------------------------------------------------------
# Structures internes
# ---------------------------------------------------------------------------

@dataclass
class TimeframeCache:
    """
    État du cache d'un timeframe.
    """

    timeframe: str
    candles: List[Candle]
    last_refresh: float = 0.0
    refreshing: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Cache principal
# ---------------------------------------------------------------------------

class Moteur2Cache:
    """
    Cache centralisé des données BiQuote du Moteur 2.

    Il ne contient aucune logique de trading.

    Son rôle est uniquement de fournir des données propres
    et disponibles aux autres modules du Moteur 2.
    """

    def __init__(
        self,
        client: Optional[BiQuoteClient] = None,
        symbol: str = SYMBOL,
    ):
        self.client = client or BiQuoteClient()

        self.symbol = symbol.upper()

        self._cache: Dict[str, TimeframeCache] = {
            timeframe: TimeframeCache(
                timeframe=timeframe,
                candles=[],
            )
            for timeframe in TIMEFRAME_REFRESH_SECONDS
        }

        # Dernier tick reçu par SignalR.
        self._latest_tick: Optional[Tick] = None

        # Verrou pour éviter deux refresh simultanés
        # du même timeframe.
        self._locks: Dict[str, asyncio.Lock] = {
            timeframe: asyncio.Lock()
            for timeframe in TIMEFRAME_REFRESH_SECONDS
        }

    # -----------------------------------------------------------------------
    # TICK TEMPS RÉEL
    # -----------------------------------------------------------------------

    def update_tick(self, tick: Any) -> None:
        """
        Met à jour le dernier prix temps réel.

        Cette méthode peut recevoir :
            - un objet Tick provenant de biquote_client.py
            - un dictionnaire provenant de biquote_stream.py
        """

        try:
            normalized = self._normalize_tick(tick)

            if normalized is None:
                return

            if normalized.symbol.upper() != self.symbol:
                return

            self._latest_tick = normalized

        except Exception:
            logger.exception(
                "Erreur lors de la mise à jour du tick Moteur 2."
            )

    def get_latest_tick(self) -> Optional[Tick]:
        """
        Retourne le dernier tick connu.
        """
        return self._latest_tick

    def get_current_price(self) -> Optional[float]:
        """
        Retourne le prix actuel basé sur le mid BiQuote.
        """

        if self._latest_tick is None:
            return None

        return self._latest_tick.mid

    # -----------------------------------------------------------------------
    # BOUGIES
    # -----------------------------------------------------------------------

    async def refresh(
        self,
        timeframe: str,
        force: bool = False,
    ) -> List[Candle]:
        """
        Rafraîchit un timeframe si nécessaire.

        force=True permet de forcer une nouvelle récupération.
        """

        timeframe = timeframe.upper()

        if timeframe not in TIMEFRAME_REFRESH_SECONDS:
            raise ValueError(
                f"Timeframe non supporté : {timeframe}"
            )

        cache = self._cache[timeframe]

        if not force and not self._needs_refresh(timeframe):
            return cache.candles

        lock = self._locks[timeframe]

        async with lock:

            # Un autre appel a peut-être déjà rafraîchi
            # les données pendant l'attente du verrou.
            if not force and not self._needs_refresh(timeframe):
                return cache.candles

            cache.refreshing = True
            cache.error = None

            try:
                logger.info(
                    "Moteur 2 | récupération %s %s",
                    self.symbol,
                    timeframe,
                )

                candles = await asyncio.to_thread(
                    self.client.get_candles,
                    self.symbol,
                    timeframe,
                    DEFAULT_LIMIT[timeframe],
                    True,
                )

                if not candles:
                    raise RuntimeError(
                        f"Aucune bougie reçue pour {timeframe}"
                    )

                cache.candles = list(candles)
                cache.last_refresh = time.time()
                cache.error = None

                logger.info(
                    "Moteur 2 | %s : %d bougies chargées",
                    timeframe,
                    len(cache.candles),
                )

                return cache.candles

            except Exception as exc:
                cache.error = str(exc)

                logger.exception(
                    "Erreur récupération %s %s",
                    self.symbol,
                    timeframe,
                )

                # Si nous possédons déjà des données valides,
                # on les conserve.
                if cache.candles:
                    return cache.candles

                raise

            finally:
                cache.refreshing = False

    async def refresh_all(
        self,
        force: bool = False,
    ) -> Dict[str, List[Candle]]:
        """
        Rafraîchit tous les timeframes nécessaires.
        """

        results = await asyncio.gather(
            *[
                self.refresh(
                    timeframe,
                    force=force,
                )
                for timeframe in TIMEFRAME_REFRESH_SECONDS
            ],
            return_exceptions=True,
        )

        output: Dict[str, List[Candle]] = {}

        for timeframe, result in zip(
            TIMEFRAME_REFRESH_SECONDS,
            results,
        ):
            if isinstance(result, Exception):
                logger.error(
                    "Refresh %s échoué : %s",
                    timeframe,
                    result,
                )
                output[timeframe] = []
            else:
                output[timeframe] = result

        return output

    # -----------------------------------------------------------------------
    # ACCÈS AUX DONNÉES
    # -----------------------------------------------------------------------

    def get_candles(
        self,
        timeframe: str,
    ) -> List[Candle]:
        """
        Retourne les bougies actuellement en cache.

        Cette méthode ne déclenche PAS de requête réseau.
        """

        timeframe = timeframe.upper()

        if timeframe not in self._cache:
            raise ValueError(
                f"Timeframe non supporté : {timeframe}"
            )

        return list(
            self._cache[timeframe].candles
        )

    def get_closed_candles(
        self,
        timeframe: str,
    ) -> List[Candle]:
        """
        Retourne les bougies clôturées.

        Le tick temps réel n'intervient jamais directement
        dans cette liste.
        """

        candles = self.get_candles(timeframe)

        return [
            candle
            for candle in candles
            if self._is_closed_candle(candle)
        ]

    def get_latest_closed_candle(
        self,
        timeframe: str,
    ) -> Optional[Candle]:
        """
        Retourne la dernière bougie clôturée.
        """

        candles = self.get_closed_candles(timeframe)

        if not candles:
            return None

        return candles[-1]

    # -----------------------------------------------------------------------
    # ÉTAT DU CACHE
    # -----------------------------------------------------------------------

    def needs_refresh(
        self,
        timeframe: str,
    ) -> bool:
        """
        Indique si un timeframe doit être rafraîchi.
        """
        timeframe = timeframe.upper()

        if timeframe not in self._cache:
            raise ValueError(
                f"Timeframe non supporté : {timeframe}"
            )

        return self._needs_refresh(timeframe)

    def _needs_refresh(
        self,
        timeframe: str,
    ) -> bool:
        cache = self._cache[timeframe]

        if not cache.candles:
            return True

        elapsed = time.time() - cache.last_refresh

        return (
            elapsed
            >= TIMEFRAME_REFRESH_SECONDS[timeframe]
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Retourne un état lisible du cache.
        """

        now = time.time()

        status: Dict[str, Any] = {
            "symbol": self.symbol,
            "current_price": self.get_current_price(),
            "tick_received": self._latest_tick is not None,
            "timeframes": {},
        }

        for timeframe, cache in self._cache.items():

            age = None

            if cache.last_refresh > 0:
                age = round(
                    now - cache.last_refresh,
                    2,
                )

            status["timeframes"][timeframe] = {
                "candles": len(cache.candles),
                "last_refresh_age": age,
                "needs_refresh": self._needs_refresh(
                    timeframe
                ),
                "refreshing": cache.refreshing,
                "error": cache.error,
            }

        return status

    # -----------------------------------------------------------------------
    # NORMALISATION TICK
    # -----------------------------------------------------------------------

    def _normalize_tick(
        self,
        tick: Any,
    ) -> Optional[Tick]:
        """
        Transforme un tick dict ou Tick en objet Tick.
        """

        if isinstance(tick, Tick):
            return tick

        if not isinstance(tick, dict):
            return None

        symbol = str(
            tick.get("symbol", self.symbol)
        ).upper()

        mid = self._safe_float(
            tick.get("mid")
        )

        if mid is None:
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
            timestamp=tick.get("timestamp"),
            market_state=tick.get(
                "marketState"
            ),
            stale=tick.get("stale"),
            quote_age_seconds=self._safe_float(
                tick.get("quoteAgeSeconds")
            ),
        )

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> Optional[float]:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_closed_candle(
        candle: Candle,
    ) -> bool:
        """
        Vérifie si une bougie est clôturée.

        Selon le modèle Candle de biquote_client.py,
        is_open=False signifie que la bougie est clôturée.
        """

        return not bool(
            getattr(candle, "is_open", False)
        )


# ---------------------------------------------------------------------------
# Test local
# ---------------------------------------------------------------------------

async def main() -> None:
    """
    Test simple du cache.

    Ce test ne lance pas SignalR.
    Il vérifie seulement la récupération des bougies BiQuote.
    """

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
    print("=" * 60)
    print("NOVA TRADE AI - TEST MOTEUR 2 CACHE")
    print("=" * 60)
    print()

    await cache.refresh(
        "H1",
        force=True,
    )

    candles = cache.get_closed_candles("H1")

    print(
        f"XAUUSD H1 : {len(candles)} "
        f"bougies clôturées"
    )

    latest = cache.get_latest_closed_candle(
        "H1"
    )

    if latest:
        print(
            "Dernière bougie H1 clôturée :"
        )
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
    print("État du cache :")
    print(cache.get_status())
    print()


if __name__ == "__main__":
    asyncio.run(main())