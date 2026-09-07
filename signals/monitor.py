"""
NOVA TRADE AI
signals/monitor.py

Moteur de surveillance automatique des signaux.

Rôle :
    SignalTracker
        ↓
    récupération du prix
        ↓
    tracker.update()
        ↓
    détection TP / SL / BE
        ↓
    notification via callback

Ce fichier ne modifie pas la logique du Tracker.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable

from core.models import SignalStatus
from signals.tracker import SignalTracker


class SignalMonitor:

    def __init__(
        self,
        tracker: SignalTracker,
        price_provider: Callable[[str], float],
        notification_callback: Callable[[str], None] | None = None,
        interval_seconds: int = 30,
    ):
        self.tracker = tracker
        self.price_provider = price_provider
        self.notification_callback = notification_callback

        self.interval_seconds = max(
            5,
            int(interval_seconds),
        )

        self._running = False
        self._thread: threading.Thread | None = None

        # Mémorise le dernier statut envoyé
        self._last_notified_status: dict[str, SignalStatus] = {}

        # Mémorise le dernier palier R notifié
        self._last_notified_r: dict[str, int] = {}

    # ==========================================================
    # DÉMARRER
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
            f"surveillance démarrée "
            f"(intervalle : {self.interval_seconds}s)"
        )

    # ==========================================================
    # ARRÊTER
    # ==========================================================

    def stop(self) -> None:

        self._running = False

        print(
            "🛑 NOVA TRADE AI — "
            "surveillance arrêtée"
        )

    # ==========================================================
    # BOUCLE PRINCIPALE
    # ==========================================================

    def _run_loop(self) -> None:

        while self._running:

            try:
                self.check_all_signals()

            except Exception as exc:

                print(
                    "⚠️ Erreur surveillance : "
                    f"{exc}"
                )

            time.sleep(
                self.interval_seconds
            )

    # ==========================================================
    # SURVEILLER TOUS LES SIGNAUX ACTIFS
    # ==========================================================

    def check_all_signals(self) -> None:

        active_signals = (
            self.tracker.active_signals()
        )

        if not active_signals:
            return

        for state in active_signals:

            try:
                self.check_signal(
                    state.signal.signal_id
                )

            except Exception as exc:

                print(
                    "⚠️ Erreur signal "
                    f"{state.signal.signal_id} : "
                    f"{exc}"
                )

    # ==========================================================
    # SURVEILLER UN SIGNAL
    # ==========================================================

    def check_signal(
        self,
        signal_id: str,
    ) -> None:

        state = self.tracker.get(
            signal_id
        )

        if state is None:
            return

        signal = state.signal

        # ------------------------------------------------------
        # Récupération du prix
        # ------------------------------------------------------

        current_price = float(
            self.price_provider(
                signal.symbol
            )
        )

        # ------------------------------------------------------
        # Ancien état
        # ------------------------------------------------------

        old_status = state.status
        old_r = state.current_r

        # ------------------------------------------------------
        # Mise à jour du tracker
        # ------------------------------------------------------

        updated_state = self.tracker.update(
            signal_id,
            current_price,
        )

        # ------------------------------------------------------
        # Notification
        # ------------------------------------------------------

        self._handle_update(
            old_status=old_status,
            old_r=old_r,
            state=updated_state,
        )

    # ==========================================================
    # TRAITEMENT DE L'ÉVOLUTION
    # ==========================================================

    def _handle_update(
        self,
        old_status: SignalStatus,
        old_r: float,
        state,
    ) -> None:

        signal = state.signal
        status = state.status
        current_r = state.current_r

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

            message = self._build_status_message(
                state
            )

            self._notify(
                message
            )

            self._last_notified_status[
                signal.signal_id
            ] = status

        # ------------------------------------------------------
        # Progression en R
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

            self._cleanup_signal(
                signal.signal_id
            )

    # ==========================================================
    # PALIERS DE R
    # ==========================================================

    def _check_r_milestone(
        self,
        state,
    ) -> None:

        signal_id = state.signal.signal_id
        current_r = state.current_r

        # Exemple :
        # 1R, 2R, 3R...
        milestone = int(
            current_r
        )

        if milestone <= 0:
            return

        last_milestone = (
            self._last_notified_r.get(
                signal_id,
                0,
            )
        )

        if milestone <= last_milestone:
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
    # MESSAGE DE STATUT
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

        status = state.status

        if status == SignalStatus.BE_RECOMMENDED:

            return (
                "🛡️ NOVA TRADE AI — BREAK-EVEN\n\n"
                f"📌 {symbol}\n"
                f"🎯 {direction}\n"
                f"💰 Prix : {price}\n"
                f"📈 R actuel : +{current_r:.2f}R\n\n"
                "⚠️ Break-Even recommandé."
            )

        if status == SignalStatus.BE_ACTIVE:

            return (
                "🛡️ NOVA TRADE AI — BE ACTIF\n\n"
                f"📌 {symbol}\n"
                f"🎯 {direction}\n"
                f"💰 Prix : {price}\n"
                f"📈 R actuel : +{current_r:.2f}R\n"
                f"🔒 BE : {state.be_price}"
            )

        if status == SignalStatus.TP_HIT:

            return (
                "🎯 NOVA TRADE AI — TAKE PROFIT\n\n"
                f"📌 {symbol}\n"
                f"🎯 {direction}\n"
                f"💰 Prix : {price}\n"
                f"📈 Résultat : +{current_r:.2f}R\n\n"
                "🏁 TP atteint.\n"
                "✅ Signal terminé."
            )

        if status == SignalStatus.SL_HIT:

            return (
                "🔴 NOVA TRADE AI — STOP LOSS\n\n"
                f"📌 {symbol}\n"
                f"🎯 {direction}\n"
                f"💰 Prix : {price}\n"
                f"📉 Résultat : {current_r:.2f}R\n\n"
                "🛑 SL atteint.\n"
                "🏁 Signal terminé."
            )

        if status == SignalStatus.INVALIDATED:

            return (
                "⚠️ NOVA TRADE AI — SIGNAL INVALIDÉ\n\n"
                f"📌 {symbol}\n"
                f"🎯 {direction}\n"
                f"💰 Prix : {price}\n\n"
                "Le signal n'est plus valide."
            )

        if status == SignalStatus.CLOSED:

            return (
                "🏁 NOVA TRADE AI — SIGNAL CLÔTURÉ\n\n"
                f"📌 {symbol}\n"
                f"🎯 {direction}\n"
                f"💰 Prix : {price}\n"
                f"📈 R final : {current_r:.2f}R"
            )

        return (
            "📊 NOVA TRADE AI — MISE À JOUR\n\n"
            f"📌 {symbol}\n"
            f"🎯 {direction}\n"
            f"💰 Prix : {price}\n"
            f"📈 R : {current_r:.2f}R"
        )

    # ==========================================================
    # MESSAGE R
    # ==========================================================

    @staticmethod
    def _build_r_message(
        state,
        milestone: int,
    ) -> str:

        signal = state.signal

        return (
            "📈 NOVA TRADE AI — PROGRESSION\n\n"
            f"📌 {signal.symbol}\n"
            f"🎯 {signal.direction.value}\n"
            f"💰 Prix : {state.current_price}\n\n"
            f"🚀 Progression : +{milestone}R\n"
            f"📊 TP : "
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
                "⚠️ Échec notification : "
                f"{exc}"
            )

    # ==========================================================
    # NETTOYAGE
    # ==========================================================

    def _cleanup_signal(
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