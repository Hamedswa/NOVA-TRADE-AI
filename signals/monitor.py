"""
NOVA TRADE AI
signals/monitor.py

Surveillance automatique des signaux actifs.

Aucune exécution réelle d'ordre.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from core.models import SignalStatus

from market_data import get_latest_price

from signals.tracker import SignalTracker


NotificationCallback = Callable[[str], None]


class SignalMonitor:

    def __init__(
        self,
        tracker: SignalTracker,
        notification_callback: Optional[
            NotificationCallback
        ] = None,
        interval_seconds: int = 30,
    ):

        self.tracker = tracker

        self.notification_callback = (
            notification_callback
        )

        self.interval_seconds = max(
            10,
            interval_seconds,
        )

        self._running = False

        self._thread: threading.Thread | None = None

        self._last_status: dict[
            str,
            SignalStatus,
        ] = {}

        self._last_milestone: dict[
            str,
            int,
        ] = {}

        self._lock = threading.Lock()

    # ========================================================
    # CALLBACK
    # ========================================================

    def set_notification_callback(
        self,
        callback: NotificationCallback | None,
    ) -> None:

        self.notification_callback = callback

    # ========================================================
    # NOTIFY
    # ========================================================

    def _notify(
        self,
        message: str,
    ) -> None:

        callback = (
            self.notification_callback
        )

        if callback is None:
            return

        try:
            callback(message)

        except Exception as exc:

            print(
                f"[MONITOR] "
                f"Erreur notification : {exc}"
            )

    # ========================================================
    # START
    # ========================================================

    def start(self) -> None:

        with self._lock:

            if self._running:
                return

            self._running = True

            self._thread = threading.Thread(
                target=self._run,
                name="nova-signal-monitor",
                daemon=True,
            )

            self._thread.start()

        print(
            "[MONITOR] Surveillance "
            "automatique démarrée."
        )

    # ========================================================
    # STOP
    # ========================================================

    def stop(self) -> None:

        with self._lock:
            self._running = False

        print(
            "[MONITOR] Surveillance "
            "automatique arrêtée."
        )

    # ========================================================
    # LOOP
    # ========================================================

    def _run(self) -> None:

        while self._running:

            try:

                self.check_all()

            except Exception as exc:

                print(
                    f"[MONITOR] "
                    f"Erreur générale : {exc}"
                )

            time.sleep(
                self.interval_seconds
            )

    # ========================================================
    # CHECK ALL
    # ========================================================

    def check_all(self) -> None:

        active_states = (
            self.tracker.active_signals()
        )

        if not active_states:
            return

        # ----------------------------------------------------
        # Un seul appel prix par symbole
        # ----------------------------------------------------

        prices: dict[str, float] = {}

        symbols = {
            state.signal.symbol
            for state in active_states
        }

        for symbol in symbols:

            try:

                price = get_latest_price(
                    symbol
                )

                if price > 0:
                    prices[symbol] = price

            except Exception as exc:

                print(
                    f"[MONITOR] "
                    f"{symbol} : prix indisponible "
                    f"({exc})"
                )

        # ----------------------------------------------------
        # UPDATE SIGNALS
        # ----------------------------------------------------

        for state in active_states:

            signal = state.signal

            symbol = signal.symbol

            if symbol not in prices:
                continue

            price = prices[symbol]

            old_status = state.status

            try:

                updated = self.tracker.update(
                    signal.signal_id,
                    price,
                )

            except Exception as exc:

                print(
                    f"[MONITOR] "
                    f"Update impossible "
                    f"{signal.signal_id}: {exc}"
                )

                continue

            new_status = updated.status

            # ------------------------------------------------
            # STATUS CHANGE
            # ------------------------------------------------

            if (
                old_status
                != new_status
            ):

                self._last_status[
                    signal.signal_id
                ] = new_status

                self._handle_status_change(
                    updated
                )

            # ------------------------------------------------
            # R MILESTONES
            # ------------------------------------------------

            self._handle_r_milestone(
                updated
            )

    # ========================================================
    # STATUS CHANGE
    # ========================================================

    def _handle_status_change(
        self,
        state,
    ) -> None:

        signal = state.signal

        if (
            state.status
            == SignalStatus.BE_RECOMMENDED
        ):

            self._notify(
                self._format_be_recommended(
                    state
                )
            )

        elif (
            state.status
            == SignalStatus.TP_HIT
        ):

            self._notify(
                self._format_tp_hit(
                    state
                )
            )

        elif (
            state.status
            == SignalStatus.SL_HIT
        ):

            self._notify(
                self._format_sl_hit(
                    state
                )
            )

    # ========================================================
    # R MILESTONES
    # ========================================================

    def _handle_r_milestone(
        self,
        state,
    ) -> None:

        signal_id = (
            state.signal.signal_id
        )

        current_r = state.current_r

        milestones = (
            1,
            2,
            3,
        )

        reached = 0

        for milestone in milestones:

            if current_r >= milestone:
                reached = milestone

        if reached <= 0:
            return

        previous = self._last_milestone.get(
            signal_id,
            0,
        )

        if reached <= previous:
            return

        self._last_milestone[
            signal_id
        ] = reached

        self._notify(
            self._format_r_milestone(
                state,
                reached,
            )
        )

    # ========================================================
    # FORMAT BE
    # ========================================================

    @staticmethod
    def _format_be_recommended(
        state,
    ) -> str:

        signal = state.signal

        return (
            "🟡 NOVA TRADE AI — BREAK EVEN\n\n"
            f"📌 {signal.symbol}\n"
            f"🎯 {signal.direction.value}\n"
            f"📈 Score : {signal.score:.2f}/100\n\n"
            f"💰 Prix actuel : "
            f"{state.current_price:.6f}\n"
            f"📊 R : {state.current_r:.2f}R\n"
            f"📈 Progression TP : "
            f"{state.progress_to_tp_percent:.1f}%\n\n"
            "⚠️ Break Even recommandé."
        )

    # ========================================================
    # FORMAT TP
    # ========================================================

    @staticmethod
    def _format_tp_hit(
        state,
    ) -> str:

        signal = state.signal

        return (
            "🟢 NOVA TRADE AI — TP ATTEINT\n\n"
            f"📌 {signal.symbol}\n"
            f"🎯 {signal.direction.value}\n\n"
            f"💰 Prix : "
            f"{state.current_price:.6f}\n"
            f"📊 R final : "
            f"{state.current_r:.2f}R\n"
            f"🏆 Meilleur R : "
            f"{state.best_r:.2f}R\n\n"
            "✅ Take Profit atteint."
        )

    # ========================================================
    # FORMAT SL
    # ========================================================

    @staticmethod
    def _format_sl_hit(
        state,
    ) -> str:

        signal = state.signal

        return (
            "🔴 NOVA TRADE AI — STOP LOSS\n\n"
            f"📌 {signal.symbol}\n"
            f"🎯 {signal.direction.value}\n\n"
            f"💰 Prix : "
            f"{state.current_price:.6f}\n"
            f"📊 R final : "
            f"{state.current_r:.2f}R\n\n"
            "❌ Stop Loss atteint."
        )

    # ========================================================
    # FORMAT R
    # ========================================================

    @staticmethod
    def _format_r_milestone(
        state,
        milestone: int,
    ) -> str:

        signal = state.signal

        return (
            "📊 NOVA TRADE AI — PROGRESSION\n\n"
            f"📌 {signal.symbol}\n"
            f"🎯 {signal.direction.value}\n\n"
            f"💰 Prix : "
            f"{state.current_price:.6f}\n"
            f"📈 R actuel : "
            f"{state.current_r:.2f}R\n"
            f"🏆 Meilleur R : "
            f"{state.best_r:.2f}R\n"
            f"🎯 TP : "
            f"{state.progress_to_tp_percent:.1f}%\n\n"
            f"✅ Niveau +{milestone}R atteint."
        )