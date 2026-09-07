"""
NOVA TRADE AI
signals/monitor.py

Moniteur automatique des signaux publiés.

Fonctions :
- suit le prix actuel des signaux actifs
- calcule la progression en R
- détecte les paliers de progression
- détecte le Break-Even
- détecte TP / SL
- envoie les notifications Telegram via un callback
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from config import CONFIG
from market_data import get_latest_price
from signals.tracker import SignalTracker
from core.models import Signal, SignalStatus


logger = logging.getLogger(__name__)


TelegramSender = Callable[[str], Awaitable[None]]


class SignalMonitor:

    # Paliers de progression en R
    R_MILESTONES = (
        0.5,
        1.0,
        1.5,
        2.0,
    )

    def __init__(
        self,
        tracker: SignalTracker,
        telegram_sender: TelegramSender,
    ):

        self.tracker = tracker
        self.telegram_sender = telegram_sender

        self._task: asyncio.Task | None = None
        self._running = False

        # Signal ID -> paliers déjà annoncés
        self._notified_r: dict[
            str,
            set[float]
        ] = {}

        # Signal ID -> BE déjà annoncé
        self._notified_be: set[str] = set()

        # Signal ID -> fin déjà annoncée
        self._notified_terminal: set[str] = set()

    # ========================================================
    # REGISTER
    # ========================================================

    def register(
        self,
        signal: Signal,
    ):

        self.tracker.register(signal)

        self._notified_r[
            signal.signal_id
        ] = set()

        logger.info(
            "Signal enregistré pour suivi: %s",
            signal.signal_id,
        )

    # ========================================================
    # FORMAT PRICE
    # ========================================================

    @staticmethod
    def _format_price(
        price: float,
    ) -> str:

        if price >= 1000:
            return f"{price:.2f}"

        if price >= 100:
            return f"{price:.3f}"

        if price >= 1:
            return f"{price:.5f}"

        return f"{price:.5f}"

    # ========================================================
    # SEND
    # ========================================================

    async def _send(
        self,
        message: str,
    ):

        try:

            await self.telegram_sender(
                message
            )

        except Exception:

            logger.exception(
                "Erreur envoi notification Telegram."
            )

    # ========================================================
    # PROGRESSION
    # ========================================================

    async def _check_progress(
        self,
        state,
    ):

        signal = state.signal
        current_r = state.current_r

        notified = self._notified_r.setdefault(
            signal.signal_id,
            set(),
        )

        crossed = [
            milestone
            for milestone in self.R_MILESTONES
            if current_r >= milestone
            and milestone not in notified
        ]

        if not crossed:
            return

        # On annonce le plus haut palier nouvellement atteint.
        milestone = max(crossed)

        for level in crossed:
            notified.add(level)

        direction = signal.direction.value

        emoji = "🟢" if current_r >= 1 else "📈"

        message = (
            f"{emoji} PROGRESSION SIGNAL\n\n"
            f"📊 Marché : {signal.symbol}\n"
            f"📌 Direction : {direction}\n"
            f"💵 Prix actuel : "
            f"{self._format_price(state.current_price)}\n\n"
            f"📈 Résultat : +{current_r:.2f}R\n"
            f"🎯 Palier atteint : +{milestone:.1f}R\n"
            f"📊 Progression TP : "
            f"{state.progress_to_tp_percent:.1f}%"
        )

        await self._send(message)

    # ========================================================
    # BREAK EVEN
    # ========================================================

    async def _check_break_even(
        self,
        state,
    ):

        signal = state.signal

        if (
            state.status
            != SignalStatus.BE_RECOMMENDED
        ):
            return

        if (
            signal.signal_id
            in self._notified_be
        ):
            return

        self._notified_be.add(
            signal.signal_id
        )

        message = (
            f"🛡️ BREAK-EVEN RECOMMANDÉ\n\n"
            f"📊 Marché : {signal.symbol}\n"
            f"📌 Direction : "
            f"{signal.direction.value}\n"
            f"💵 Prix actuel : "
            f"{self._format_price(state.current_price)}\n\n"
            f"📈 Résultat : "
            f"+{state.current_r:.2f}R\n"
            f"🎯 Progression TP : "
            f"{state.progress_to_tp_percent:.1f}%\n\n"
            f"⚠️ Le signal a atteint "
            f"le seuil de Break-Even."
        )

        await self._send(message)

    # ========================================================
    # TERMINAL
    # ========================================================

    async def _check_terminal(
        self,
        state,
    ):

        signal = state.signal
        status = state.status

        if status not in {
            SignalStatus.TP_HIT,
            SignalStatus.SL_HIT,
        }:
            return

        if (
            signal.signal_id
            in self._notified_terminal
        ):
            return

        self._notified_terminal.add(
            signal.signal_id
        )

        if status == SignalStatus.TP_HIT:

            message = (
                f"🎯 TP ATTEINT\n\n"
                f"📊 Marché : {signal.symbol}\n"
                f"📌 Direction : "
                f"{signal.direction.value}\n"
                f"💵 Prix final : "
                f"{self._format_price(state.current_price)}\n\n"
                f"✅ Résultat : "
                f"+{state.current_r:.2f}R\n"
                f"📈 Meilleur R : "
                f"+{state.best_r:.2f}R"
            )

        else:

            message = (
                f"🛑 STOP LOSS ATTEINT\n\n"
                f"📊 Marché : {signal.symbol}\n"
                f"📌 Direction : "
                f"{signal.direction.value}\n"
                f"💵 Prix final : "
                f"{self._format_price(state.current_price)}\n\n"
                f"❌ Résultat : "
                f"{state.current_r:.2f}R\n"
                f"📉 Pire R : "
                f"{state.worst_r:.2f}R"
            )

        await self._send(message)

    # ========================================================
    # UPDATE ONE SIGNAL
    # ========================================================

    async def update_signal(
        self,
        signal_id: str,
    ):

        state = self.tracker.get(
            signal_id
        )

        if state is None:
            return

        signal = state.signal

        try:

            price = await asyncio.to_thread(
                get_latest_price,
                signal.symbol,
            )

            state = self.tracker.update(
                signal_id,
                price,
            )

            await self._check_progress(
                state
            )

            await self._check_break_even(
                state
            )

            await self._check_terminal(
                state
            )

        except Exception:

            logger.exception(
                "Erreur suivi signal %s",
                signal_id,
            )

    # ========================================================
    # MONITOR ONCE
    # ========================================================

    async def monitor_once(self):

        states = list(
            self.tracker.active_signals()
        )

        if not states:
            return

        for state in states:

            await self.update_signal(
                state.signal.signal_id
            )

            # Petite pause pour éviter
            # une rafale de requêtes API.
            await asyncio.sleep(1)

    # ========================================================
    # LOOP
    # ========================================================

    async def _loop(self):

        interval = max(
            30,
            int(
                CONFIG.TRACKING_INTERVAL_SECONDS
            ),
        )

        logger.info(
            "Signal Monitor démarré. "
            "Intervalle: %ss",
            interval,
        )

        while self._running:

            try:

                await self.monitor_once()

            except asyncio.CancelledError:
                raise

            except Exception:

                logger.exception(
                    "Erreur dans la boucle Signal Monitor."
                )

            await asyncio.sleep(
                interval
            )

    # ========================================================
    # START
    # ========================================================

    def start(self):

        if self._running:
            return

        self._running = True

        self._task = asyncio.create_task(
            self._loop()
        )

        logger.info(
            "Signal Monitor lancé."
        )

    # ========================================================
    # STOP
    # ========================================================

    async def stop(self):

        self._running = False

        if self._task is not None:

            self._task.cancel()

            try:
                await self._task

            except asyncio.CancelledError:
                pass

            self._task = None

        logger.info(
            "Signal Monitor arrêté."
        )