"""
NOVA TRADE AI
signals/tracker.py

Suivi des signaux actifs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from config import CONFIG

from core.models import (
    Signal,
    SignalState,
    SignalStatus,
)

from risk.risk_manager import calculate_be_price


class SignalTracker:

    def __init__(self):

        self._states: dict[
            str,
            SignalState
        ] = {}

    # ========================================================
    # REGISTER
    # ========================================================

    def register(
        self,
        signal: Signal,
    ) -> SignalState:

        state = SignalState(
            signal=signal,
            current_price=signal.entry,
        )

        self._states[
            signal.signal_id
        ] = state

        return state

    # ========================================================
    # GET
    # ========================================================

    def get(
        self,
        signal_id: str,
    ) -> SignalState | None:

        return self._states.get(
            signal_id
        )

    # ========================================================
    # FIND ACTIVE SIGNAL BY SYMBOL
    # ========================================================

    def find_active_by_symbol(
        self,
        symbol: str,
    ) -> SignalState | None:

        active_statuses = {
            SignalStatus.ACTIVE,
            SignalStatus.BE_RECOMMENDED,
            SignalStatus.BE_ACTIVE,
        }

        for state in self._states.values():

            if (
                state.signal.symbol == symbol
                and state.status in active_statuses
            ):
                return state

        return None

    # ========================================================
    # ACTIVE SIGNALS
    # ========================================================

    def active_signals(
        self,
    ) -> list[SignalState]:

        active_statuses = {
            SignalStatus.ACTIVE,
            SignalStatus.BE_RECOMMENDED,
            SignalStatus.BE_ACTIVE,
        }

        return [
            state
            for state in self._states.values()
            if state.status in active_statuses
        ]

    # ========================================================
    # R CALCULATION
    # ========================================================

    @staticmethod
    def calculate_r(
        signal: Signal,
        price: float,
    ) -> float:

        risk = signal.risk_distance

        if risk <= 0:
            return 0.0

        if signal.direction.value == "BUY":

            return (
                price - signal.entry
            ) / risk

        return (
            signal.entry - price
        ) / risk

    # ========================================================
    # UPDATE
    # ========================================================

    def update(
        self,
        signal_id: str,
        current_price: float,
    ) -> SignalState:

        if signal_id not in self._states:

            raise KeyError(
                f"Signal inconnu: {signal_id}"
            )

        state = self._states[
            signal_id
        ]

        signal = state.signal

        previous_status = state.status

        state.current_price = (
            current_price
        )

        state.current_r = round(
            self.calculate_r(
                signal,
                current_price,
            ),
            4,
        )

        state.best_r = max(
            state.best_r,
            state.current_r,
        )

        state.worst_r = min(
            state.worst_r,
            state.current_r,
        )

        # ----------------------------------------------------
        # PROGRESSION TP
        # ----------------------------------------------------

        tp_distance = abs(
            signal.take_profit
            - signal.entry
        )

        if tp_distance > 0:

            if (
                signal.direction.value
                == "BUY"
            ):

                progress = (
                    current_price
                    - signal.entry
                ) / tp_distance

            else:

                progress = (
                    signal.entry
                    - current_price
                ) / tp_distance

            state.progress_to_tp_percent = round(
                max(
                    0.0,
                    min(
                        100.0,
                        progress * 100,
                    ),
                ),
                2,
            )

        # ----------------------------------------------------
        # DISTANCES
        # ----------------------------------------------------

        state.distance_to_sl = abs(
            current_price
            - signal.stop_loss
        )

        state.distance_to_tp = abs(
            signal.take_profit
            - current_price
        )

        # ----------------------------------------------------
        # TP / SL
        # ----------------------------------------------------

        if (
            signal.direction.value
            == "BUY"
        ):

            sl_hit = (
                current_price
                <= signal.stop_loss
            )

            tp_hit = (
                current_price
                >= signal.take_profit
            )

        else:

            sl_hit = (
                current_price
                >= signal.stop_loss
            )

            tp_hit = (
                current_price
                <= signal.take_profit
            )

        if tp_hit:

            state.status = (
                SignalStatus.TP_HIT
            )

        elif sl_hit:

            state.status = (
                SignalStatus.SL_HIT
            )

        # ----------------------------------------------------
        # BREAK EVEN
        # ----------------------------------------------------

        elif (
            state.current_r
            >= CONFIG.BE_TRIGGER_R
            and state.be_price is None
            and state.status
            != SignalStatus.BE_ACTIVE
        ):

            state.status = (
                SignalStatus.BE_RECOMMENDED
            )

        state.last_update = (
            datetime.now(
                timezone.utc
            )
        )

        return state

    # ========================================================
    # ACTIVATE BREAK EVEN
    # ========================================================

    def activate_be(
        self,
        signal_id: str,
    ) -> SignalState:

        state = self._states[
            signal_id
        ]

        signal = state.signal

        buffer = (
            CONFIG.BE_BUFFER_R
            * signal.risk_distance
        )

        state.be_price = calculate_be_price(
            signal.entry,
            signal.direction.value,
            buffer,
        )

        state.status = (
            SignalStatus.BE_ACTIVE
        )

        state.last_update = (
            datetime.now(
                timezone.utc
            )
        )

        return state