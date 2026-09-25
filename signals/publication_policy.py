from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from storage import get_storage

WINDOW_HOURS = 12
MAX_PUBLICATIONS = 3
MAX_PER_SYMBOL = 1

def _parse(value: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _symbol(signal: Any) -> str:
    value = signal.get("symbol", "") if isinstance(signal, dict) else getattr(signal, "symbol", "")
    return str(value).upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")

class PublicationPolicy:
    """Plafond de publication persistant; ne produit aucune decision."""
    def __init__(self, storage=None, window_hours: int = WINDOW_HOURS,
                 max_publications: int = MAX_PUBLICATIONS,
                 max_per_symbol: int = MAX_PER_SYMBOL) -> None:
        self.storage = storage or get_storage()
        self.window = timedelta(hours=max(1, int(window_hours)))
        self.max_publications = max(1, int(max_publications))
        self.max_per_symbol = max(1, int(max_per_symbol))

    def status(self, symbol: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        cutoff = now - self.window
        recent = []
        for signal in self.storage.list_signals():
            published = _parse(signal.get("published_at"))
            if published and published >= cutoff:
                recent.append(signal)
        normalized = _symbol({"symbol": symbol}) if symbol else None
        per_symbol = sum(1 for item in recent if _symbol(item) == normalized) if normalized else 0
        return {
            "allowed_total": len(recent) < self.max_publications,
            "allowed_symbol": per_symbol < self.max_per_symbol if normalized else True,
            "recent_count": len(recent), "symbol_count": per_symbol,
            "remaining_total": max(0, self.max_publications - len(recent)),
            "window_hours": int(self.window.total_seconds() // 3600),
            "max_publications": self.max_publications,
            "max_per_symbol": self.max_per_symbol,
        }

    def can_publish(self, signal: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        symbol = _symbol(signal)
        state = self.status(symbol, now)
        allowed = bool(state["allowed_total"] and state["allowed_symbol"])
        reason = "ALLOWED" if allowed else ("12H_GLOBAL_LIMIT" if not state["allowed_total"] else "12H_SYMBOL_LIMIT")
        return {**state, "allowed": allowed, "reason": reason, "symbol": symbol}

publication_policy = PublicationPolicy()

def can_publish_signal(signal: Any) -> Dict[str, Any]:
    return publication_policy.can_publish(signal)
