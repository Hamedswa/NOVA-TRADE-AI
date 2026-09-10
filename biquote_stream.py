import asyncio
import logging
from typing import Any, Callable, Optional

from pysignalr.client import SignalRClient


logger = logging.getLogger(__name__)


BIQUOTE_HUB_URL = "https://biquote.io/hubs/tick"
SYMBOL = "XAUUSD"


class BiQuoteStream:
    """
    Flux temps réel BiQuote via SignalR.

    Rôle :
    - se connecter au hub BiQuote
    - s'abonner à XAUUSD
    - recevoir les ticks ReceiveTick
    - normaliser les données
    - transmettre chaque tick au callback
    """

    def __init__(
        self,
        symbol: str = SYMBOL,
        on_tick: Optional[Callable[[dict[str, Any]], Any]] = None,
    ):
        self.symbol = symbol.upper()
        self.on_tick_callback = on_tick

        self.client: Optional[SignalRClient] = None
        self.running = False

    async def _on_open(self) -> None:
        """
        Appelé lorsque la connexion SignalR est ouverte.
        """
        logger.info("BiQuote SignalR connecté")

        try:
            await self.client.send(
                "Subscribe",
                [[self.symbol]],
            )

            logger.info(
                "Abonnement BiQuote actif : %s",
                self.symbol,
            )

        except Exception:
            logger.exception(
                "Erreur lors de l'abonnement à %s",
                self.symbol,
            )

    async def _on_close(self) -> None:
        """
        Appelé lorsque la connexion est fermée.
        """
        logger.warning("BiQuote SignalR déconnecté")

    async def _on_error(self, error: Any) -> None:
        """
        Gestion des erreurs SignalR.
        """
        logger.error(
            "Erreur BiQuote SignalR : %s",
            getattr(error, "error", error),
        )

    async def _on_receive_tick(self, data: Any) -> None:
        """
        Réception d'un événement ReceiveTick.
        """

        try:
            if not data:
                return

            # BiQuote renvoie normalement une liste
            # contenant le tick.
            tick = data[0] if isinstance(data, list) else data

            if not isinstance(tick, dict):
                logger.warning(
                    "Tick BiQuote inattendu : %r",
                    tick,
                )
                return

            symbol = str(
                tick.get("symbol", "")
            ).upper()

            if symbol != self.symbol:
                return

            bid = tick.get("bid")
            ask = tick.get("ask")
            mid = tick.get("mid")

            if mid is None:
                logger.warning(
                    "Tick %s sans mid : %r",
                    self.symbol,
                    tick,
                )
                return

            normalized = {
                "symbol": symbol,
                "bid": self._to_float(bid),
                "ask": self._to_float(ask),
                "mid": self._to_float(mid),
                "spread": self._to_float(
                    tick.get("spread")
                ),
                "timestamp": tick.get("timestamp"),
                "marketState": tick.get(
                    "marketState"
                ),
                "stale": tick.get("stale"),
                "quoteAgeSeconds": self._to_float(
                    tick.get("quoteAgeSeconds")
                ),
            }

            logger.info(
                "TICK %s | bid=%s ask=%s mid=%s",
                symbol,
                normalized["bid"],
                normalized["ask"],
                normalized["mid"],
            )

            if self.on_tick_callback is not None:
                result = self.on_tick_callback(normalized)

                if asyncio.iscoroutine(result):
                    await result

        except Exception:
            logger.exception(
                "Erreur traitement ReceiveTick"
            )

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """
        Conversion sécurisée en float.
        """
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def run(self) -> None:
        """
        Lance le flux temps réel.

        pysignalr gère le cycle de connexion.
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
            "Démarrage BiQuote Stream pour %s",
            self.symbol,
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
                "Erreur critique BiQuote Stream"
            )

        finally:
            self.running = False


async def main() -> None:
    """
    Test autonome du flux BiQuote.
    """

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
    )

    stream = BiQuoteStream(
        symbol="XAUUSD"
    )

    await stream.run()


if __name__ == "__main__":
    asyncio.run(main())