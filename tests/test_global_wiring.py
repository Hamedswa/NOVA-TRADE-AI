from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from storage import SQLiteStorage
from signals.publication_policy import PublicationPolicy


def test_publication_policy_3_in_12h_and_one_per_symbol():
    with tempfile.TemporaryDirectory() as tmp:
        db = SQLiteStorage(str(Path(tmp) / "test.db"))
        policy = PublicationPolicy(storage=db)
        now = datetime.now(timezone.utc)

        for i, symbol in enumerate(("XAUUSD", "BTCUSD", "EURUSD")):
            db.save_signal({
                "signal_id": f"S{i}", "symbol": symbol, "direction": "BUY",
                "published_at": (now - timedelta(minutes=10+i)).isoformat(),
                "state": "PUBLISHED",
            })

        blocked = policy.can_publish({"symbol": "GBPUSD"}, now=now)
        assert blocked["allowed"] is False
        assert blocked["reason"] == "12H_GLOBAL_LIMIT"


def test_publication_policy_blocks_same_symbol():
    with tempfile.TemporaryDirectory() as tmp:
        db = SQLiteStorage(str(Path(tmp) / "test.db"))
        policy = PublicationPolicy(storage=db)
        now = datetime.now(timezone.utc)
        db.save_signal({
            "signal_id": "S1", "symbol": "BTCUSD", "direction": "BUY",
            "published_at": now.isoformat(), "state": "PUBLISHED",
        })
        result = policy.can_publish({"symbol": "BTCUSD"}, now=now)
        assert result["allowed"] is False
        assert result["reason"] == "12H_SYMBOL_LIMIT"


def test_storage_opportunity_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db = SQLiteStorage(str(Path(tmp) / "test.db"))
        db.save_opportunity({
            "opportunity_id": "OPP-1", "symbol": "EURUSD",
            "lifecycle_state": "MATURE", "payload": {"maturity": 66},
        })
        rows = db.list_opportunities("EURUSD")
        assert rows and rows[0]["opportunity_id"] == "OPP-1"
        assert rows[0]["payload"]["maturity"] == 66
