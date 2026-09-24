"""Surveillance de santé des composants NOVA TRADE AI."""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, Optional

from signals.storage import SQLiteStorage, get_storage


@dataclass
class HealthStatus:
    component: str
    status: str
    checked_at: str
    latency_ms: Optional[float] = None
    message: str = ""
    details: Dict[str, Any] = None

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["details"] = self.details or {}
        return data


class SystemHealth:
    """Registre les checks sans décider de la stratégie."""

    def __init__(self, storage: Optional[SQLiteStorage] = None) -> None:
        self.storage = storage or get_storage()
        self.last: Dict[str, HealthStatus] = {}

    def check(
        self,
        component: str,
        checker: Callable[[], Any],
    ) -> HealthStatus:
        started = time.perf_counter()
        try:
            result = checker()
            status = "OK"
            message = "OK"
            details = result if isinstance(result, dict) else {"result": result}
        except Exception as exc:
            status = "ERROR"
            message = str(exc)
            details = {"exception": type(exc).__name__}
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        from signals.storage import utc_now_iso
        item = HealthStatus(component, status, utc_now_iso(), latency_ms, message, details)
        self.last[component] = item
        self.storage.record_health(component, status, latency_ms, message, details)
        return item

    def record(
        self,
        component: str,
        status: str,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        latency_ms: Optional[float] = None,
    ) -> HealthStatus:
        from signals.storage import utc_now_iso
        item = HealthStatus(component, status.upper(), utc_now_iso(), latency_ms, message, details or {})
        self.last[component] = item
        self.storage.record_health(component, item.status, latency_ms, message, details or {})
        return item

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {name: status.as_dict() for name, status in self.last.items()}


system_health = SystemHealth()
