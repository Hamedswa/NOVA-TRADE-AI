"""
NOVA TRADE AI - Moteur 2
moteur2_cache.py
Cache centralisé des données BiQuote pour le Moteur 2.
Actifs :
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
# Rafraîchissement maximum autorisé.
#
# Ce sont des fenêtres de rafraîchissement du cache,
# pas des règles de trading.
TIMEFRAME_REFRESH_SECONDS = {
    "H4": 8 * 60 * 60,
    "H1": 2 * 60 * 60,
    "M15": 30 * 60,
    "M5": 10 * 60,
    "M1": 60,
}
# Nombre maximum de bougies conservées.
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
    Organisation interne :
        symbol
          |
          +-- H4
          +-- H1
          +-- M15
          +-- M5
          +-- M1
    Exemple :
        XAUUSD -> H4/H1/M15/M5/M1
        BTCUSD -> H4/H1/M15/M5/M1
        EURUSD -> H4/H1/M15/M5/M1
        GBPUSD -> H4/H1/M15/M5/M1
    Ce module :
        - stocke les bougies
        - stocke les derniers ticks
        - gère la fraîcheur
        - gère les refresh
        - fournit les données aux autres modules
    Ce module ne :
        - détecte pas de setup
        - calcule pas d'Entry
        - calcule pas de SL/TP
        - calcule pas de RR
        - ne valide aucun signal
        - ne bloque aucun signal
    """
    def __init__(
        self,
        client: Optional[BiQuoteClient] = None,
        symbols: Optional[
            list[str] | tuple[str, ...]
        ] = None,
    ):
        self.client = client or BiQuoteClient()
        # ------------------------------------------------------------------
        # Symboles
        # ------------------------------------------------------------------
        if symbols is None:
            symbols = SUPPORTED_SYMBOLS
        normalized_symbols: List[str] = []
        for symbol in symbols:
            normalized = self._normalize_symbol(
                symbol
            )
            if not normalized:
                continue
            if normalized not in SUPPORTED_SYMBOLS:
                logger.warning(
                    "Symbole ignoré dans le cache : %s",
                    symbol,
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
        #
        # _cache["XAUUSD"]["H4"]
        # _cache["BTCUSD"]["M1"]
        # etc.
        # ------------------------------------------------------------------
        self._cache: Dict[
            str,
            Dict[str, TimeframeCache],
        ] = {
            symbol: {
                timeframe: TimeframeCache(
                    timeframe=timeframe,
                    candles=[],
                )
                for timeframe in SUPPORTED_TIMEFRAMES
            }
            for symbol in self.symbols
        }
        # ------------------------------------------------------------------
        # Dernier tick par symbole
        # ------------------------------------------------------------------
        self._latest_ticks: Dict[
            str,
            Tick,
        ] = {}
        # ------------------------------------------------------------------
        # Lock indépendant pour chaque
        # symbole + timeframe.
        # ------------------------------------------------------------------
        self._locks: Dict[
            str,
            Dict[str, asyncio.Lock],
        ] = {
            symbol: {
                timeframe: asyncio.Lock()
                for timeframe in SUPPORTED_TIMEFRAMES
            }
            for symbol in self.symbols
        }
    # =========================================================================
    # SYMBOL HELPERS
    # =========================================================================
    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:
        """
        Normalise un symbole.
        Exemples :
            XAU/USD -> XAUUSD
            BTC-USD -> BTCUSD
            EUR USD -> EURUSD
        """
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
        """
        Valide et normalise un symbole.
        """
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
        """
        Valide et normalise un timeframe.
        """
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
        """
        Met à jour le dernier tick d'un symbole.
        Peut recevoir :
            - Tick
            - dict provenant de biquote_stream.py
        Le tick est stocké uniquement pour son symbole.
        """
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
        symbol: str,
    ) -> Optional[Tick]:
        """
        Retourne le dernier tick connu d'un symbole.
        """
        normalized = self._validate_symbol(
            symbol
        )
        return self._latest_ticks.get(
            normalized
        )
    def get_current_price(
        self,
        symbol: str,
    ) -> Optional[float]:
        """
        Retourne le dernier prix mid connu
        pour le symbole demandé.
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
        """
        Retourne les derniers ticks connus.
        Une copie du dictionnaire est retournée.
        """
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
        """
        Rafraîchit un timeframe pour un symbole.
        IMPORTANT :
        Le nouveau biquote_client.py utilise :
            get_candles(
                timeframe,
                symbol,
                limit,
                closed_only
            )
        Le cache respecte donc cet ordre.
        """
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
        # ------------------------------------------------------------------
        # Pas besoin de réseau si les données sont
        # encore suffisamment fraîches.
        # ------------------------------------------------------------------
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
            # Un autre appel a peut-être terminé
            # le refresh pendant l'attente.
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
                # ------------------------------------------------------------------
                # BiQuote REST
                #
                # closed_only=True
                #
                # Les bougies utilisées par le moteur
                # sont donc explicitement demandées comme
                # bougies clôturées.
                # ------------------------------------------------------------------
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
                # ------------------------------------------------------------------
                # Protection supplémentaire.
                #
                # On ne stocke que des objets Candle valides.
                # ------------------------------------------------------------------
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
                # ------------------------------------------------------------------
                # IMPORTANT :
                #
                # En cas d'erreur réseau temporaire,
                # les anciennes données restent disponibles.
                #
                # Mais leur état d'erreur est exposé dans
                # get_status().
                # ------------------------------------------------------------------
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
        """
        Rafraîchit tous les timeframes d'un symbole.
        """
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
        """
        Rafraîchit tous les timeframes de tous
        les symboles configurés.
        Structure retournée :
            {
                "XAUUSD": {
                    "H4": [...],
                    "H1": [...],
                    ...
                },
                "BTCUSD": {
                    ...
                }
            }
        """
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
        symbol: str,
        timeframe: str,
    ) -> List[Candle]:
        """
        Retourne les bougies actuellement en cache.
        Aucune requête réseau n'est déclenchée.
        """
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
        symbol: str,
        timeframe: str,
    ) -> List[Candle]:
        """
        Retourne uniquement les bougies clôturées.
        Le tick temps réel n'intervient jamais
        dans cette liste.
        """
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
        symbol: str,
        timeframe: str,
    ) -> Optional[Candle]:
        """
        Retourne la dernière bougie clôturée.
        """
        candles = self.get_closed_candles(
            symbol,
            timeframe,
        )
        if not candles:
            return None
        return candles[-1]
    def get_symbol_data(
        self,
        symbol: str,
    ) -> Dict[
        str,
        List[Candle],
    ]:
        """
        Retourne toutes les bougies en cache
        pour un symbole.
        """
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
        """
        Indique si un timeframe doit être rafraîchi.
        """
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
        """
        Vérification interne de fraîcheur.
        """
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
        """
        Retourne l'état complet du cache.
        Les informations sont organisées par symbole
        puis par timeframe.
        """
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
        # ------------------------------------------------------------------
        # Ticks
        # ------------------------------------------------------------------
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
        # ------------------------------------------------------------------
        # Bougies
        # ------------------------------------------------------------------
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
        """
        Transforme un dictionnaire tick en objet Tick.
        Si l'objet est déjà un Tick, il est utilisé
        directement.
        """
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
        """
        Conversion sécurisée en float.
        """
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
        """
        Détermine si une bougie est clôturée.
        Selon le modèle Candle de biquote_client.py :
            is_open=False -> bougie clôturée.
        """
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
    """
    Test local du cache.
    Ce test :
        - crée le cache multi-actifs
        - récupère H1 pour les quatre actifs
        - affiche les dernières bougies
        - affiche l'état du cache
    Il ne lance pas SignalR.
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
        except Exception as exc:
            print(
                f"Erreur {symbol} : {exc}"
            )
        print()
    print("=" * 70)
    print("ÉTAT DU CACHE")
    print("=" * 70)
    print(
        cache.get_status()
    )
    print()
if __name__ == "__main__":
    asyncio.run(main())