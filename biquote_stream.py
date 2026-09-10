"""
NOVA TRADE AI
Moteur 2 — Flux temps réel BiQuote

Responsabilités :
- connexion au hub SignalR BiQuote ;
- abonnement à XAUUSD ;
- réception des ticks ;
- normalisation ;
- reconnexion automatique ;
- transmission des ticks au callback du moteur.

Aucune logique de trading ici.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from signalrcore.hub_connection_builder import HubConnectionBuilder


logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

BIQUOTE_HUB_URL = "https://biquote.io/hubs/tick"

SYMBOL = "XAUUSD"

RECONNECT_DELAY_SECONDS = 5

MAX_RECONNECT_DELAY_SECONDS = 60


# ============================================================
# MODÈLE TICK
# ============================================================

@dataclass(frozen=True)
class LiveTick:
    symbol: str

    bid: float
    ask: float
    mid: float

    spread: float

    timestamp: str

    received_at: str

    source: str = "biquote"

    stale: bool = False


# ============================================================
# EXCEPTIONS
# ============================================================

class BiQuoteStreamError(Exception):
    """Erreur du flux temps réel BiQuote."""


# ============================================================
# STREAM
# ============================================================

class BiQuoteStream:

    def __init__(
        self,
        symbol: str = SYMBOL,
        callback: Optional[
            Callable[[LiveTick], Any]
        ] = None,
    ) -> None:

        self.symbol = symbol.upper()

        self.callback = callback

        self.connection = None

        self.running = False

        self.connected = False

        self._reconnect_delay = RECONNECT_DELAY_SECONDS

    # ========================================================
    # CALLBACK
    # ========================================================

    def set_callback(
        self,
        callback: Callable[[LiveTick], Any],
    ) -> None:

        self.callback = callback

    # ========================================================
    # NORMALISATION
    # ========================================================

    def _normalize_tick(
        self,
        data: Any,
    ) -> LiveTick:

        if isinstance(data, list):

            if not data:
                raise BiQuoteStreamError(
                    "Tick vide reçu."
                )

            data = data[0]

        if not isinstance(data, dict):

            raise BiQuoteStreamError(
                f"Format tick inattendu: {type(data)}"
            )

        try:

            bid = float(data["bid"])

            ask = float(data["ask"])

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:

            raise BiQuoteStreamError(
                f"Tick BiQuote invalide: {data}"
            ) from exc

        mid_value = data.get("mid")

        if mid_value is None:

            mid = (bid + ask) / 2

        else:

            mid = float(mid_value)

        spread_value = data.get("spread")

        if spread_value is None:

            spread = ask - bid

        else:

            spread = float(spread_value)

        timestamp = str(
            data.get(
                "timestamp",
                "",
            )
        )

        received_at = datetime.now(
            timezone.utc
        ).isoformat()

        return LiveTick(
            symbol=str(
                data.get(
                    "symbol",
                    self.symbol,
                )
            ).upper(),

            bid=bid,

            ask=ask,

            mid=mid,

            spread=spread,

            timestamp=timestamp,

            received_at=received_at,

            stale=bool(
                data.get(
                    "stale",
                    False,
                )
            ),
        )

    # ========================================================
    # RÉCEPTION
    # ========================================================

    def _on_tick(
        self,
        data: Any,
    ) -> None:

        try:

            tick = self._normalize_tick(data)

        except Exception as exc:

            logger.warning(
                "Tick BiQuote ignoré: %s",
                exc,
            )

            return

        if tick.symbol != self.symbol:

            return

        if tick.bid <= 0 or tick.ask <= 0:

            logger.warning(
                "Prix BiQuote invalide: bid=%s ask=%s",
                tick.bid,
                tick.ask,
            )

            return

        if tick.ask < tick.bid:

            logger.warning(
                "Spread incohérent: bid=%s ask=%s",
                tick.bid,
                tick.ask,
            )

            return

        logger.debug(
            "Tick %s | bid=%.5f ask=%.5f mid=%.5f",
            tick.symbol,
            tick.bid,
            tick.ask,
            tick.mid,
        )

        if self.callback is None:

            return

        try:

            result = self.callback(tick)

            if inspect.isawaitable(result):

                try:
                    loop = asyncio.get_running_loop()

                    loop.create_task(result)

                except RuntimeError:

                    asyncio.run(result)

        except Exception:

            logger.exception(
                "Erreur dans le callback du flux BiQuote."
            )

    # ========================================================
    # CONNEXION
    # ========================================================

    def _build_connection(self) -> None:

        self.connection = (
            HubConnectionBuilder()
            .with_url(
                BIQUOTE_HUB_URL
            )
            .with_automatic_reconnect(
                {
                    "type": "raw",
                    "keep_alive_interval": 10,
                    "reconnect_interval": 5,
                    "max_attempts": 0,
                }
            )
            .build()
        )

        self.connection.on(
            "ReceiveTick",
            self._on_tick,
        )

        self.connection.on_open(
            self._on_open
        )

        self.connection.on_close(
            self._on_close
        )

        self.connection.on_error(
            self._on_error
        )

    # ========================================================
    # ÉVÉNEMENTS
    # ========================================================

    def _on_open(self) -> None:

        self.connected = True

        self._reconnect_delay = (
            RECONNECT_DELAY_SECONDS
        )

        logger.info(
            "Connexion BiQuote établie."
        )

        self._subscribe()

    def _on_close(self) -> None:

        self.connected = False

        logger.warning(
            "Connexion BiQuote fermée."
        )

    def _on_error(
        self,
        error: Any,
    ) -> None:

        self.connected = False

        logger.error(
            "Erreur flux BiQuote: %s",
            error,
        )

    # ========================================================
    # ABONNEMENT
    # ========================================================

    def _subscribe(self) -> None:

        if self.connection is None:

            raise BiQuoteStreamError(
                "Connexion BiQuote inexistante."
            )

        logger.info(
            "Abonnement BiQuote: %s",
            self.symbol,
        )

        self.connection.send(
            "Subscribe",
            [
                self.symbol,
            ],
        )

    # ========================================================
    # START
    # ========================================================

    def start(self) -> None:

        if self.running:

            logger.warning(
                "Flux BiQuote déjà démarré."
            )

            return

        self.running = True

        self._build_connection()

        try:

            self.connection.start()

            logger.info(
                "Flux temps réel BiQuote démarré."
            )

        except Exception as exc:

            self.connected = False

            logger.exception(
                "Impossible de démarrer "
                "le flux BiQuote."
            )

            raise BiQuoteStreamError(
                "Échec démarrage flux BiQuote."
            ) from exc

    # ========================================================
    # STOP
    # ========================================================

    def stop(self) -> None:

        self.running = False

        self.connected = False

        if self.connection is not None:

            try:

                self.connection.stop()

            except Exception:

                logger.exception(
                    "Erreur lors de l'arrêt "
                    "du flux BiQuote."
                )

        self.connection = None

        logger.info(
            "Flux BiQuote arrêté."
        )

    # ========================================================
    # ÉTAT
    # ========================================================

    def is_connected(self) -> bool:

        return bool(
            self.connected
        )


# ============================================================
# INSTANCE PAR DÉFAUT
# ============================================================

biquote_stream = BiQuoteStream()