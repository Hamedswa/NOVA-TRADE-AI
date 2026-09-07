"""
NOVA TRADE AI
signals/runtime.py

Runtime central des signaux.
"""

from __future__ import annotations

from signals.monitor import SignalMonitor
from signals.tracker import SignalTracker


# ============================================================
# SINGLETONS
# ============================================================

signal_tracker = SignalTracker()

signal_monitor = SignalMonitor(
    tracker=signal_tracker,
    interval_seconds=30,
)


# ============================================================
# START
# ============================================================

def start_signal_monitor() -> None:

    signal_monitor.start()


# ============================================================
# REGISTER
# ============================================================

def register_signal(signal):

    # --------------------------------------------------------
    # Anti-duplication par symbole
    # --------------------------------------------------------

    existing = (
        signal_tracker.find_active_by_symbol(
            signal.symbol
        )
    )

    if existing is not None:

        return existing, False

    state = signal_tracker.register(
        signal
    )

    return state, True