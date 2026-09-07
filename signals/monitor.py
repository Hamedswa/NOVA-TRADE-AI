"""
NOVA TRADE AI
signals/monitor.py

Surveillance automatique des signaux actifs.

Flux :

SignalTracker
    ↓
market_data.get_latest_price()
    ↓
tracker.update()
    ↓
TP / SL / BE / progression
    ↓
notification_callback
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from config import CONFIG
from core.models import SignalStatus
from market_data import get_latest_price
from signals.tracker import SignalTracker


class SignalMonitor:

    def __init__(
        self,
        tracker: SignalTracker,
        notification_callback: Callable[[str], None] | None = None,
        interval_seconds: int = 30,
    ):
        self.tracker = tracker
        self.notification_callback = (
            notification_callback
        )

        self.interval_seconds = max(
            10,
            int(interval_seconds),
        )

        self._running = False
        self._thread: threading.Thread | None = None

        self._last_notified_status: dict[
            str,
            SignalStatus,
        ] = {}

        self._last_notified_r: dict[
            str,
            int,
        ] = {}

    # ==========================================================
    # START
    # ==========================================================

    def start(self) -> None:

        if self._running:
            return

        self._running = True

        self._thread = threading.Thread(
            target=self._run_loop,
            name="nova-signal-monitor",
            daemon=True,
        )

        self._thread.start()

        print(
            "👁️ NOVA TRADE AI — "
            f"surveillance active "
            f"({self.interval_seconds}s)"
        )

    # ==========================================================
    # STOP
    # ==========================================================

    def stop(self) -> None:

        self._running = False

        print(
            "🛑 NOVA TRADE AI — "
            "surveillance arrêtée"
        )

    # ==========================================================
    # BOUCLE
    # ==========================================================

    def _run_loop(self) -> None:

        while self._running:

            try:

                self.check_all_signals()

            except Exception as exc:

                print(
                    "⚠️ Erreur globale surveillance : "
                    f"{exc}"
                )

            time.sleep(
                self.interval_seconds
            )

    # ==========================================================
    # TOUS LES SIGNAUX
    # ==========================================================

    def check_all_signals(self) -> None:

        active_signals = (
            self.tracker.active_signals()
        )

        if not active_signals:
            return

        # ------------------------------------------------------
        # Un seul prix par symbole
        # ------------------------------------------------------

        prices: dict[str, float] = {}

        for state in active_signals:

            symbol = state.signal.symbol

            if symbol in prices:
                continue

            try:

                prices[symbol] = float(
                    get_latest_price(symbol)
                )

            except Exception as exc:

                print(
                    f"⚠️ Prix indisponible "
                    f"{symbol}: {exc}"
                )

        # ------------------------------------------------------
        # Mise à jour des signaux
        # ------------------------------------------------------

        for state in active_signals:

            symbol = state.signal.symbol

            if symbol not in prices:
                continue

            try:

                self.check_signal(
                    state.signal.signal_id,
                    prices[symbol],
                )

            except Exception as exc:

                print(
                    "⚠️ Erreur signal "
                    f"{state.signal.signal_id}: "
                    f"{exc}"
                )

    # ==========================================================
    # SIGNAL INDIVIDUEL
    # ==========================================================

    def check_signal(
        self,
        signal_id: str,
        current_price: float,
    ) -> None:

        state = self.tracker.get(
            signal_id
        )

        if state is None:
            return

        old_status = state.status

        updated_state = (
            self.tracker.update(
                signal_id,
                current_price,
            )
        )

        self._handle_update(
            old_status,
            updated_state,
        )

    # ==========================================================
    # TRAITEMENT
    # ==========================================================

    def _handle_update(
        self,
        old_status: SignalStatus,
        state,
    ) -> None:

        signal = state.signal
        status = state.status

        # ------------------------------------------------------
        # Changement de statut
        # ------------------------------------------------------

        last_status = (
            self._last_notified_status.get(
                signal.signal_id
            )
        )

        if (
            status != old_status
            and status != last_status
        ):

            self._notify(
                self._build_status_message(
                    state
                )
            )

            self._last_notified_status[
                signal.signal_id
            ] = status

        # ------------------------------------------------------
        # Paliers de R
        # ------------------------------------------------------

        self._check_r_milestone(
            state
        )

        # ------------------------------------------------------
        # Signal terminé
        # ------------------------------------------------------

        if status in {
            SignalStatus.TP_HIT,
            SignalStatus.SL_HIT,
            SignalStatus.INVALIDATED,
            SignalStatus.CLOSED,
        }:

            self._cleanup(
                signal.signal_id
            )

    # ==========================================================
    # PALIERS R
    # ==========================================================

    def _check_r_milestone(
        self,
        state,
    ) -> None:

        signal_id = state.signal.signal_id

        current_r = state.current_r

        milestone = int(
            current_r
        )

        if milestone <= 0:
            return

        previous = (
            self._last_notified_r.get(
                signal_id,
                0,
            )
        )

        if milestone <= previous:
            return

        self._last_notified_r[
            signal_id
        ] = milestone

        self._notify(
            self._build_r_message(
                state,
                milestone,
            )
        )

    # ==========================================================
    # MESSAGE STATUT
    # ==========================================================

    @staticmethod
    def _build_status_message(
        state,
    ) -> str:

        signal = state.signal

        symbol = signal.symbol
        direction = signal.direction.value
        price = state.current_price
        current_r = state.current_r

        if state.status == SignalStatus.BE_RECOMMENDED:

            return (
                "🛡️ NOVA TRADE AI\n\n"
                "BREAK-EVEN RECOMMANDÉ\n\n"
                f"📌 Marché : {symbol}\n"
                f"🎯 Direction : {direction}\n"
                f"💰 Prix : {price}\n"
                f"📈 R actuel : +{current_r:.2f}R\n\n"
                "⚠️ Le niveau de protection "
                "peut être déplacé au BE."
            )

        if state.status == SignalStatus.TP_HIT:

            return (
                "🎯 NOVA TRADE AI\n\n"
                "TAKE PROFIT ATTEINT ✅\n\n"
                f"📌 Marché : {symbol}\n"
                f"🎯 Direction : {direction}\n"
                f"💰 Prix : {price}\n"
                f"📈 Résultat : +{current_r:.2f}R\n\n"
                "🏁 Signal terminé."
            )

        if state.status == SignalStatus.SL_HIT:

            return (
                "🔴 NOVA TRADE AI\n\n"
                "STOP LOSS ATTEINT\n\n"
                f"📌 Marché : {symbol}\n"
                f"🎯 Direction : {direction}\n"
                f"💰 Prix : {price}\n"
                f"📉 Résultat : {current_r:.2f}R\n\n"
                "🏁 Signal terminé."
            )

        if state.status == SignalStatus.INVALIDATED:

            return (
                "⚠️ NOVA TRADE AI\n\n"
                "SIGNAL INVALIDÉ\n\n"
                f"📌 Marché : {symbol}\n"
                f"🎯 Direction : {direction}\n"
                f"💰 Prix : {price}\n\n"
                "Le setup n'est plus valide."
            )

        if state.status == SignalStatus.CLOSED:

            return (
                "🏁 NOVA TRADE AI\n\n"
                "SIGNAL CLÔTURÉ\n\n"
                f"📌 Marché : {symbol}\n"
                f"🎯 Direction : {direction}\n"
                f"💰 Prix : {price}\n"
                f"📊 R final : {current_r:.2f}R"
            )

        return (
            "📊 NOVA TRADE AI\n\n"
            "MISE À JOUR DU SIGNAL\n\n"
            f"📌 Marché : {symbol}\n"
            f"🎯 Direction : {direction}\n"
            f"💰 Prix : {price}\n"
            f"📈 R : {current_r:.2f}R"
        )

    # ==========================================================
    # MESSAGE PROGRESSION
    # ==========================================================

    @staticmethod
    def _build_r_message(
        state,
        milestone: int,
    ) -> str:

        signal = state.signal

        return (
            "📈 NOVA TRADE AI\n\n"
            "PROGRESSION DU SIGNAL\n\n"
            f"📌 Marché : {signal.symbol}\n"
            f"🎯 Direction : "
            f"{signal.direction.value}\n"
            f"💰 Prix : {state.current_price}\n\n"
            f"🚀 Progression : +{milestone}R\n"
            f"📊 TP atteint : "
            f"{state.progress_to_tp_percent:.2f}%"
        )

    # ==========================================================
    # NOTIFICATION
    # ==========================================================

    def _notify(
        self,
        message: str,
    ) -> None:

        if self.notification_callback is None:

            print()
            print(message)
            print()

            return

        try:

            self.notification_callback(
                message
            )

        except Exception as exc:

            print(
                "⚠️ Erreur notification Telegram : "
                f"{exc}"
            )

    # ==========================================================
    # NETTOYAGE
    # ==========================================================

    def _cleanup(
        self,
        signal_id: str,
    ) -> None:

        self._last_notified_status.pop(
            signal_id,
            None,
        )

        self._last_notified_r.pop(
            signal_id,
            None,
        )