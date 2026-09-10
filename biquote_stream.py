import asyncio
import logging
from typing import Any, Callable, Optional

from pysignalr.client import SignalRClient


logger = logging.getLogger(__name__)


# ============================================================
# BIQUOTE SIGNALR
# ============================================================

BIQUOTE_HUB_URL = "https://biquote.io/hubs/tick"

SUPPORTED_SYMBOLS = (
    "XAUUSD",
    "BTCUSD",
    "EURUSD",
    "GBPUSD",
)


# ============================================================
# HELPERS
# ============================================================

def normalize_symbol(symbol: str) -> str:
    """
    Normalise un symbole utilisateur / fournisseur.

    Exemples :
        XAU/USD -> XAUUSD
        EUR/USD -> EURUSD
        BTC-USD -> BTCUSD
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


def is_supported_symbol(symbol: str) -> bool:
    """
    Vérifie qu'un symbole appartient à l'univers
    du Moteur 2.
    """

    return normalize_symbol(symbol) in SUPPORTED_SYMBOLS


# ============================================================
# BIQUOTE STREAM
# ============================================================

class BiQuoteStream:
    """
    Flux temps réel BiQuote via SignalR.

    Architecture :

        BiQuote SignalR
              |
              v
        ReceiveTick
              |
              v
        normalisation
              |
              +---- XAUUSD
              +---- BTCUSD
              +---- EURUSD
              +---- GBPUSD
              |
              v
        callback global

    Rôle EXCLUSIF :
    - connexion au hub BiQuote
    - abonnement aux symboles
    - réception des ticks
    - normalisation
    - transmission au callback

    Ce module ne contient :
    - aucune logique de trading
    - aucune validation
    - aucun calcul de signal
    - aucun calcul de RR
    - aucun score
    """

    def __init__(
        self,
        symbols: Optional[list[str] | tuple[str, ...]] = None,
        on_tick: Optional[Callable[[dict[str, Any]], Any]] = None,
    ):
        if symbols is None:
            symbols = SUPPORTED_SYMBOLS

        normalized_symbols = []

        for symbol in symbols:
            normalized = normalize_symbol(symbol)

            if not normalized:
                continue

            if normalized not in SUPPORTED_SYMBOLS:
                logger.warning(
                    "Symbole BiQuote ignoré car non supporté : %s",
                    symbol,
                )
                continue

            if normalized not in normalized_symbols:
                normalized_symbols.append(normalized)

        if not normalized_symbols:
            raise ValueError(
                "Aucun symbole BiQuote valide n'a été fourni."
            )

        self.symbols = tuple(normalized_symbols)

        self.on_tick_callback = on_tick

        self.client: Optional[SignalRClient] = None

        self.running = False

        # Dernier tick reçu par symbole.
        self.latest_ticks: dict[str, dict[str, Any]] = {}

        # État de connexion.
        self.connected = False

    # ========================================================
    # CONNECTION CALLBACKS
    # ========================================================

    async def _on_open(self) -> None:
        """
        Appelé lorsque la connexion SignalR est ouverte.
        """

        self.connected = True

        logger.info(
            "BiQuote SignalR connecté."
        )

        try:
            # BiQuote attend une liste de symboles.
            #
            # Exemple documenté :
            # Subscribe(["EURUSD", "XAUUSD", "BTCUSD"])
            #
            # Avec pysignalr, l'appel est transmis comme :
            # send("Subscribe", [symbols])
            await self.client.send(
                "Subscribe",
                [list(self.symbols)],
            )

            logger.info(
                "Abonnement BiQuote actif : %s",
                ", ".join(self.symbols),
            )

        except Exception:
            logger.exception(
                "Erreur lors de l'abonnement BiQuote."
            )

    async def _on_close(self) -> None:
        """
        Appelé lorsque la connexion est fermée.
        """

        self.connected = False

        logger.warning(
            "BiQuote SignalR déconnecté."
        )

    async def _on_error(self, error: Any) -> None:
        """
        Gestion des erreurs SignalR.
        """

        logger.error(
            "Erreur BiQuote SignalR : %s",
            getattr(error, "error", error),
        )

    # ========================================================
    # TICK HANDLER
    # ========================================================

    async def _on_receive_tick(self, data: Any) -> None:
        """
        Réception et normalisation d'un événement ReceiveTick.

        BiQuote renvoie normalement le tick dans une structure
        contenant un dictionnaire.
        """

        try:
            if not data:
                return

            tick = self._extract_tick(data)

            if tick is None:
                logger.warning(
                    "Tick BiQuote inattendu : %r",
                    data,
                )
                return

            symbol = normalize_symbol(
                tick.get("symbol", "")
            )

            if not symbol:
                logger.warning(
                    "Tick BiQuote sans symbole : %r",
                    tick,
                )
                return

            # Sécurité : seuls les symboles souscrits sont acceptés.
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

            # Le mid est indispensable au moteur.
            if mid is None or mid <= 0:
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
                "quoteAgeSeconds": self._to_float(
                    tick.get(
                        "quoteAgeSeconds"
                    )
                ),
            }

            # Sécurité supplémentaire :
            # si bid/ask existent, ils doivent être positifs.
            if normalized["bid"] is not None:
                if normalized["bid"] <= 0:
                    logger.warning(
                        "Bid invalide pour %s : %s",
                        symbol,
                        normalized["bid"],
                    )
                    return

            if normalized["ask"] is not None:
                if normalized["ask"] <= 0:
                    logger.warning(
                        "Ask invalide pour %s : %s",
                        symbol,
                        normalized["ask"],
                    )
                    return

            # Stockage local du dernier tick.
            self.latest_ticks[symbol] = normalized

            logger.debug(
                "TICK %s | bid=%s ask=%s mid=%s",
                symbol,
                normalized["bid"],
                normalized["ask"],
                normalized["mid"],
            )

            # Transmission au système supérieur.
            if self.on_tick_callback is not None:

                result = self.on_tick_callback(
                    normalized
                )

                if asyncio.iscoroutine(result):
                    await result

        except Exception:
            logger.exception(
                "Erreur traitement ReceiveTick."
            )

    # ========================================================
    # TICK EXTRACTION
    # ========================================================

    @staticmethod
    def _extract_tick(
        data: Any,
    ) -> Optional[dict[str, Any]]:
        """
        Extrait le dictionnaire tick de la réponse SignalR.

        pysignalr peut fournir l'événement sous forme de liste.
        """

        if isinstance(data, dict):
            return data

        if isinstance(data, list):

            if not data:
                return None

            # Cas normal :
            # [ { ...tick... } ]
            first = data[0]

            if isinstance(first, dict):
                return first

        return None

    # ========================================================
    # PUBLIC ACCESS
    # ========================================================

    def get_latest_tick(
        self,
        symbol: str,
    ) -> Optional[dict[str, Any]]:
        """
        Retourne le dernier tick reçu pour un symbole.
        """

        normalized = normalize_symbol(symbol)

        return self.latest_ticks.get(
            normalized
        )

    def get_latest_price(
        self,
        symbol: str,
    ) -> Optional[float]:
        """
        Retourne le dernier mid connu.
        """

        tick = self.get_latest_tick(
            symbol
        )

        if tick is None:
            return None

        return tick.get("mid")

    def get_all_latest_ticks(
        self,
    ) -> dict[str, dict[str, Any]]:
        """
        Retourne une copie des derniers ticks
        connus pour tous les symboles.
        """

        return dict(
            self.latest_ticks
        )

    # ========================================================
    # CONVERSION
    # ========================================================

    @staticmethod
    def _to_float(
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

    # ========================================================
    # RUN
    # ========================================================

    async def run(self) -> None:
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

        # Enregistrement des callbacks.
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
            ", ".join(self.symbols),
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
                "Erreur critique BiQuote Stream."
            )

        finally:

            self.running = False
            self.connected = False

            logger.info(
                "BiQuote Stream terminé."
            )


# ============================================================
# TEST AUTONOME
# ============================================================

async def main() -> None:
    """
    Test autonome du flux BiQuote.

    Les quatre marchés sont abonnés simultanément.
    """

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
            f"[BIQUOTE] "
            f"{tick['symbol']} | "
            f"mid={tick['mid']} | "
            f"bid={tick['bid']} | "
            f"ask={tick['ask']}"
        )

    stream = BiQuoteStream(
        symbols=SUPPORTED_SYMBOLS,
        on_tick=on_tick,
    )

    await stream.run()


if __name__ == "__main__":
    asyncio.run(main())