"""
NOVA TRADE AI — ENGINE 2
biquote_stream.py

Flux temps réel BiQuote via SignalR.

ENGINE 2 :
    XAUUSD
    BTCUSD
    GBPUSD
    EURUSD

Rôle de ce module :
    - connexion SignalR BiQuote
    - abonnement aux symboles supportés
    - réception des ticks
    - normalisation
    - transmission au moteur

Aucune logique de trading.
Aucun score.
Aucun RR.
Aucune validation.
Aucune décision BUY/SELL.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from pysignalr.client import SignalRClient


logger = logging.getLogger(
    "NOVA_ENGINE_2.BIQUOTE_STREAM"
)


# ============================================================================
# CONFIGURATION
# ============================================================================

BIQUOTE_HUB_URL = (
    "https://biquote.io/hubs/tick"
)


SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "GBPUSD",
    "EURUSD",
)


# ============================================================================
# HELPERS
# ============================================================================

def normalize_symbol(
    symbol: str,
) -> str:
    """
    Normalise un symbole.

    Exemples :
        XAU/USD -> XAUUSD
        XAU-USD -> XAUUSD
        xauusd  -> XAUUSD
        BTC/USD -> BTCUSD
    """

    if not isinstance(
        symbol,
        str,
    ):
        return ""

    return (
        symbol
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
        .strip()
    )


def is_supported_symbol(
    symbol: str,
) -> bool:
    """
    Vérifie que le symbole appartient
    à l'univers Engine 2.
    """

    return (
        normalize_symbol(symbol)
        in SUPPORTED_SYMBOLS
    )


# ============================================================================
# BIQUOTE STREAM
# ============================================================================

class BiQuoteStream:
    """
    Flux temps réel BiQuote via SignalR.

    Le constructeur accepte volontairement
    les deux formes :

        BiQuoteStream(
            symbol="XAUUSD",
            on_tick=...
        )

    et :

        BiQuoteStream(
            symbols=["XAUUSD"],
            on_tick=...
        )

    Cela garantit la compatibilité avec
    moteur2.py et évite le conflit
    symbol / symbols.
    """

    def __init__(
        self,
        symbol: Optional[str] = None,
        symbols: Optional[
            list[str] | tuple[str, ...]
        ] = None,
        on_tick: Optional[
            Callable[
                [dict[str, Any]],
                Any,
            ]
        ] = None,
    ) -> None:

        # --------------------------------------------------------------------
        # COMPATIBILITÉ symbol / symbols
        # --------------------------------------------------------------------

        requested_symbols: list[str] = []

        if symbol is not None:
            requested_symbols.append(
                symbol
            )

        if symbols is not None:

            if isinstance(
                symbols,
                str,
            ):
                requested_symbols.append(
                    symbols
                )

            else:
                requested_symbols.extend(
                    list(symbols)
                )

        # Si aucun symbole n'est fourni,
        # Engine 2 utilise XAUUSD par défaut.
        if not requested_symbols:
            requested_symbols = [
                "XAUUSD"
            ]

        # --------------------------------------------------------------------
        # NORMALISATION
        # --------------------------------------------------------------------

        normalized_symbols: list[str] = []

        for requested in requested_symbols:

            normalized = normalize_symbol(
                requested
            )

            if not normalized:
                continue

            if (
                normalized
                not in SUPPORTED_SYMBOLS
            ):
                logger.warning(
                    "Symbole BiQuote ignoré "
                    "car non supporté : %s",
                    requested,
                )
                continue

            if (
                normalized
                not in normalized_symbols
            ):
                normalized_symbols.append(
                    normalized
                )

        if not normalized_symbols:
            raise ValueError(
                "Aucun symbole BiQuote valide. "
                "Symboles supportés : "
                f"{', '.join(SUPPORTED_SYMBOLS)}"
            )

        # --------------------------------------------------------------------
        # ÉTAT
        # --------------------------------------------------------------------

        self.symbols = tuple(
            normalized_symbols
        )

        # Compatibilité directe
        # pour le moteur.
        self.symbol = self.symbols[0]

        self.on_tick_callback = on_tick

        self.client: Optional[
            SignalRClient
        ] = None

        self.running = False

        self.connected = False

        self.latest_ticks: dict[
            str,
            dict[str, Any],
        ] = {}

        logger.info(
            "BiQuoteStream initialisé | "
            "symbol=%s | symbols=%s",
            self.symbol,
            self.symbols,
        )

    # =========================================================================
    # CONNECTION CALLBACKS
    # =========================================================================

    async def _on_open(
        self,
    ) -> None:
        """
        Appelé lorsque SignalR est connecté.
        """

        self.connected = True

        logger.info(
            "BiQuote SignalR connecté."
        )

        try:

            # BiQuote attend une liste
            # de symboles.
            await self.client.send(
                "Subscribe",
                [list(self.symbols)],
            )

            logger.info(
                "Abonnement BiQuote actif : %s",
                ", ".join(
                    self.symbols
                ),
            )

        except Exception:
            logger.exception(
                "Erreur lors de "
                "l'abonnement BiQuote."
            )

    async def _on_close(
        self,
    ) -> None:
        """
        Appelé lorsque SignalR se déconnecte.
        """

        self.connected = False

        logger.warning(
            "BiQuote SignalR déconnecté."
        )

    async def _on_error(
        self,
        error: Any,
    ) -> None:
        """
        Gestion des erreurs SignalR.
        """

        logger.error(
            "Erreur BiQuote SignalR : %s",
            getattr(
                error,
                "error",
                error,
            ),
        )

    # =========================================================================
    # TICK HANDLER
    # =========================================================================

    async def _on_receive_tick(
        self,
        data: Any,
    ) -> None:
        """
        Réception et normalisation
        d'un événement ReceiveTick.
        """

        try:

            if not data:
                return

            tick = self._extract_tick(
                data
            )

            if tick is None:

                logger.warning(
                    "Tick BiQuote inattendu : %r",
                    data,
                )

                return

            symbol = normalize_symbol(
                tick.get(
                    "symbol",
                    "",
                )
            )

            if not symbol:

                logger.warning(
                    "Tick BiQuote sans symbole : %r",
                    tick,
                )

                return

            # ----------------------------------------------------------------
            # SÉCURITÉ
            # ----------------------------------------------------------------

            if symbol not in self.symbols:
                return

            bid = self._to_float(
                tick.get("bid")
            )

            ask = self._to_float(
                tick.get("ask")
            )

            mid = self._to_float(
                tick.get("mid")
            )

            # Le mid est indispensable.
            if (
                mid is None
                or mid <= 0
            ):

                logger.warning(
                    "Tick %s invalide : mid=%r",
                    symbol,
                    tick.get("mid"),
                )

                return

            normalized = {

                "symbol": symbol,

                "bid": bid,

                "ask": ask,

                "mid": mid,

                "spread": self._to_float(
                    tick.get("spread")
                ),

                "timestamp": tick.get(
                    "timestamp"
                ),

                "marketState": tick.get(
                    "marketState"
                ),

                "stale": tick.get(
                    "stale"
                ),

                "quoteAgeSeconds":
                    self._to_float(
                        tick.get(
                            "quoteAgeSeconds"
                        )
                    ),
            }

            # ----------------------------------------------------------------
            # VALIDATION BID
            # ----------------------------------------------------------------

            if (
                normalized["bid"]
                is not None
            ):

                if (
                    normalized["bid"]
                    <= 0
                ):

                    logger.warning(
                        "Bid invalide pour %s : %s",
                        symbol,
                        normalized["bid"],
                    )

                    return

            # ----------------------------------------------------------------
            # VALIDATION ASK
            # ----------------------------------------------------------------

            if (
                normalized["ask"]
                is not None
            ):

                if (
                    normalized["ask"]
                    <= 0
                ):

                    logger.warning(
                        "Ask invalide pour %s : %s",
                        symbol,
                        normalized["ask"],
                    )

                    return

            # ----------------------------------------------------------------
            # STOCKAGE
            # ----------------------------------------------------------------

            self.latest_ticks[
                symbol
            ] = normalized

            logger.debug(
                "TICK %s | bid=%s | ask=%s | mid=%s",
                symbol,
                normalized["bid"],
                normalized["ask"],
                normalized["mid"],
            )

            # ----------------------------------------------------------------
            # CALLBACK MOTEUR
            # ----------------------------------------------------------------

            if (
                self.on_tick_callback
                is not None
            ):

                result = (
                    self.on_tick_callback(
                        normalized
                    )
                )

                if asyncio.iscoroutine(
                    result
                ):

                    await result

        except Exception:

            logger.exception(
                "Erreur traitement ReceiveTick."
            )

    # =========================================================================
    # TICK EXTRACTION
    # =========================================================================

    @staticmethod
    def _extract_tick(
        data: Any,
    ) -> Optional[
        dict[str, Any]
    ]:
        """
        Extrait le dictionnaire tick
        de la réponse SignalR.
        """

        if isinstance(
            data,
            dict,
        ):

            return data

        if isinstance(
            data,
            list,
        ):

            if not data:
                return None

            first = data[0]

            if isinstance(
                first,
                dict,
            ):

                return first

        return None

    # =========================================================================
    # PUBLIC ACCESS
    # =========================================================================

    def get_latest_tick(
        self,
        symbol: str,
    ) -> Optional[
        dict[str, Any]
    ]:

        normalized = normalize_symbol(
            symbol
        )

        return self.latest_ticks.get(
            normalized
        )

    def get_latest_price(
        self,
        symbol: str,
    ) -> Optional[float]:

        tick = self.get_latest_tick(
            symbol
        )

        if tick is None:
            return None

        return tick.get(
            "mid"
        )

    def get_all_latest_ticks(
        self,
    ) -> dict[
        str,
        dict[str, Any],
    ]:

        return dict(
            self.latest_ticks
        )

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @staticmethod
    def _to_float(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        try:

            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

    # =========================================================================
    # START — COMPATIBILITÉ MOTEUR 2
    # =========================================================================

    async def start(
        self,
    ) -> None:
        """
        Alias de compatibilité avec moteur2.py.

        Le moteur appelle start().
        Le flux réel est exécuté par run().
        """

        await self.run()

    # =========================================================================
    # RUN
    # =========================================================================

    async def run(
        self,
    ) -> None:
        """
        Lance le flux temps réel BiQuote.
        """

        if self.running:

            logger.warning(
                "BiQuoteStream est déjà en cours."
            )

            return

        self.running = True

        self.client = SignalRClient(
            BIQUOTE_HUB_URL
        )

        # --------------------------------------------------------------------
        # CALLBACKS SIGNALR
        # --------------------------------------------------------------------

        self.client.on_open(
            self._on_open
        )

        self.client.on_close(
            self._on_close
        )

        self.client.on_error(
            self._on_error
        )

        self.client.on(
            "ReceiveTick",
            self._on_receive_tick,
        )

        logger.info(
            "Démarrage BiQuote Stream."
        )

        logger.info(
            "Symboles : %s",
            ", ".join(
                self.symbols
            ),
        )

        try:

            await self.client.run()

        except asyncio.CancelledError:

            logger.info(
                "BiQuote Stream arrêté."
            )

            raise

        except Exception:

            logger.exception(
                "Erreur critique "
                "BiQuote Stream."
            )

        finally:

            self.running = False

            self.connected = False

            logger.info(
                "BiQuote Stream terminé."
            )

    # =========================================================================
    # STOP
    # =========================================================================

    async def stop(
        self,
    ) -> None:
        """
        Arrêt propre du flux.
        """

        self.running = False

        self.connected = False

        logger.info(
            "Arrêt demandé pour BiQuote Stream."
        )


# ============================================================================
# TEST AUTONOME
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

    async def on_tick(
        tick: dict[str, Any],
    ) -> None:

        print(
            "[BIQUOTE] "
            f"{tick['symbol']} | "
            f"mid={tick['mid']} | "
            f"bid={tick['bid']} | "
            f"ask={tick['ask']}"
        )

    # Utilisation identique
    # à moteur2.py.
    stream = BiQuoteStream(
        symbol="XAUUSD",
        on_tick=on_tick,
    )

    await stream.run()


if __name__ == "__main__":

    asyncio.run(
        main()
    )