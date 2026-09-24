"""Journal métier du Moteur 2.

Couche volontairement simple au-dessus de SQLiteStorage.
Elle transforme les événements techniques en événements lisibles du journal.
Aucune décision de trading n'est prise ici.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from signals.storage import SQLiteStorage, get_storage, utc_now_iso


class SignalJournal:
    def __init__(self, storage: Optional[SQLiteStorage] = None) -> None:
        self.storage = storage or get_storage()

    @staticmethod
    def _value(obj: Any, *names: str, default: Any = None) -> Any:
        for name in names:
            if isinstance(obj, dict) and name in obj:
                return obj[name]
            if hasattr(obj, name):
                return getattr(obj, name)
        return default

    def record_publication(self, signal: Any, published_at: Optional[str] = None) -> str:
        signal_id = str(self._value(signal, "signal_id", "id", "setup_id", default="") or "")
        if not signal_id:
            raise ValueError("Signal sans identifiant stable.")
        payload = {
            "signal_id": signal_id,
            "symbol": str(self._value(signal, "symbol", default="")),
            "direction": str(self._value(signal, "direction", default="")),
            "setup_type": self._value(signal, "setup_type", "setup", default=None),
            "scenario": self._value(signal, "scenario", default=None),
            "published_at": published_at or utc_now_iso(),
            "entry": self._value(signal, "entry", "entry_price", default=None),
            "stop_loss": self._value(signal, "stop_loss", "sl", "stop", default=None),
            "tp1": self._value(signal, "tp1", "tp_1", "take_profit", "take_profit_1", default=None),
            "tp2": self._value(signal, "tp2", "tp_2", "take_profit_2", default=None),
            "tp3": self._value(signal, "tp3", "tp_3", "take_profit_3", default=None),
            "rr": self._value(signal, "rr", "primary_rr", default=None),
            "score": self._value(signal, "score", default=None),
            "confidence": self._value(signal, "confidence", default=None),
            "state": "PUBLISHED",
            "metadata": self._value(signal, "metadata", default={}) or {},
        }
        self.storage.save_signal(payload)
        self.storage.record_signal_event(signal_id, "PUBLISHED", price=payload["entry"], payload=payload)
        return signal_id

    def record_tracking_event(
        self,
        signal_id: str,
        event_type: str,
        price: Optional[float] = None,
        r_value: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.storage.record_signal_event(signal_id, event_type, price=price, r_value=r_value, payload=payload)

    def record_state_update(
        self,
        signal_id: str,
        state: str,
        current_price: Optional[float] = None,
        current_r: Optional[float] = None,
        best_r: Optional[float] = None,
        worst_r: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        current = self.storage.get_signal(signal_id)
        if current is None:
            raise KeyError(f"Signal inconnu : {signal_id}")
        current.update({
            "state": state,
            "current_price": current_price if current_price is not None else current.get("current_price"),
            "current_r": current_r if current_r is not None else current.get("current_r"),
            "best_r": best_r if best_r is not None else current.get("best_r", 0),
            "worst_r": worst_r if worst_r is not None else current.get("worst_r", 0),
            "closed_at": utc_now_iso() if state in {"CLOSED", "SL_HIT", "TP1_HIT", "TP2_HIT", "TP3_HIT", "TP_HIT"} else current.get("closed_at"),
        })
        self.storage.save_signal(current)
        self.storage.record_signal_event(signal_id, f"STATE:{state}", price=current_price, r_value=current_r, payload=payload)

    def get(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return self.storage.get_signal(signal_id)

    def events(self, signal_id: str):
        return self.storage.list_signal_events(signal_id)
