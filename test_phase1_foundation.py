from pathlib import Path

from config import (
    CONFIG,
    MINIMUM_RR,
    MIN_RR,
    RR_REFERENCE,
    SCORE_REFERENCE,
    SUPPORTED_SYMBOLS,
    TIMEFRAMES,
)
from signals.journal import SignalJournal
from signals.storage import SQLiteStorage
from system_health import SystemHealth


def test_universe_and_timeframes():
    assert SUPPORTED_SYMBOLS == ("XAUUSD", "BTCUSD", "EURUSD", "GBPUSD")
    assert TIMEFRAMES == ("H4", "H1", "M15", "M5", "M1")


def test_rr_and_score_are_references_not_blockers():
    assert RR_REFERENCE == 3.0
    assert MINIMUM_RR == 0.0
    assert MIN_RR == 0.0
    assert SCORE_REFERENCE == 60
    assert CONFIG.BE_TRIGGER_R == 1.0


def test_storage_survives_new_instance(tmp_path: Path):
    db = tmp_path / "nova.sqlite3"
    first = SQLiteStorage(str(db))
    first.save_signal({
        "signal_id": "SIG-001",
        "symbol": "XAUUSD",
        "direction": "BUY",
        "published_at": "2026-09-24T20:00:00+00:00",
        "entry": 2650.0,
        "stop_loss": 2640.0,
        "tp1": 2680.0,
        "rr": 3.0,
        "state": "PUBLISHED",
        "metadata": {"test": True},
    })
    first.record_signal_event("SIG-001", "PUBLISHED", price=2650.0)

    second = SQLiteStorage(str(db))
    signal = second.get_signal("SIG-001")
    assert signal is not None
    assert signal["symbol"] == "XAUUSD"
    assert signal["metadata"]["test"] is True
    assert len(second.list_signal_events("SIG-001")) == 1


def test_journal_and_health(tmp_path: Path):
    db = SQLiteStorage(str(tmp_path / "journal.sqlite3"))
    journal = SignalJournal(db)
    signal_id = journal.record_publication({
        "signal_id": "SIG-002",
        "symbol": "BTCUSD",
        "direction": "SELL",
        "entry": 100000,
        "stop_loss": 101000,
        "tp1": 97000,
    })
    assert signal_id == "SIG-002"
    journal.record_state_update("SIG-002", "TP1_HIT", current_price=97000, current_r=3.0)
    assert journal.get("SIG-002")["state"] == "TP1_HIT"

    health = SystemHealth(db)
    result = health.check("test", lambda: {"alive": True})
    assert result.status == "OK"
    assert health.snapshot()["test"]["details"]["alive"] is True
