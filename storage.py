"""Persistance SQLite du Moteur 2.

Ce module ne décide jamais BUY/SELL/WAIT.
Il fournit uniquement une persistance transactionnelle pour :
- signaux publiés ;
- événements de suivi ;
- opportunités observées ;
- état de santé des composants.

SQLite est choisi pour rester autonome sur iSH et survivre aux redémarrages.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from config import SIGNAL_DB_PATH


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _path(path: Optional[str] = None) -> Path:
    raw = path or SIGNAL_DB_PATH
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


class SQLiteStorage:
    """Stockage local thread-safe par connexion courte."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = _path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    setup_type TEXT,
                    scenario TEXT,
                    published_at TEXT NOT NULL,
                    entry REAL,
                    stop_loss REAL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    rr REAL,
                    score REAL,
                    confidence REAL,
                    state TEXT NOT NULL DEFAULT 'PUBLISHED',
                    current_price REAL,
                    current_r REAL,
                    best_r REAL DEFAULT 0,
                    worst_r REAL DEFAULT 0,
                    closed_at TEXT,
                    final_result TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_signals_symbol_published
                    ON signals(symbol, published_at);
                CREATE INDEX IF NOT EXISTS idx_signals_state
                    ON signals(state);

                CREATE TABLE IF NOT EXISTS signal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    price REAL,
                    r_value REAL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
                );

                CREATE INDEX IF NOT EXISTS idx_signal_events_signal_time
                    ON signal_events(signal_id, event_at);

                CREATE TABLE IF NOT EXISTS opportunities (
                    opportunity_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_opportunities_symbol_state
                    ON opportunities(symbol, lifecycle_state);

                CREATE TABLE IF NOT EXISTS health_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    latency_ms REAL,
                    message TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_health_component_time
                    ON health_events(component, checked_at);
                """
            )

    def save_signal(self, signal: Dict[str, Any]) -> None:
        required = ("signal_id", "symbol", "direction", "published_at")
        missing = [key for key in required if not signal.get(key)]
        if missing:
            raise ValueError("Signal incomplet : " + ", ".join(missing))

        metadata = signal.get("metadata", {})
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO signals (
                    signal_id, symbol, direction, setup_type, scenario,
                    published_at, entry, stop_loss, tp1, tp2, tp3, rr,
                    score, confidence, state, current_price, current_r,
                    best_r, worst_r, closed_at, final_result, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    current_price=excluded.current_price,
                    current_r=excluded.current_r,
                    best_r=excluded.best_r,
                    worst_r=excluded.worst_r,
                    state=excluded.state,
                    closed_at=excluded.closed_at,
                    final_result=excluded.final_result,
                    metadata_json=excluded.metadata_json
                """,
                (
                    str(signal["signal_id"]), str(signal["symbol"]), str(signal["direction"]),
                    signal.get("setup_type"), signal.get("scenario"), str(signal["published_at"]),
                    signal.get("entry"), signal.get("stop_loss"), signal.get("tp1"),
                    signal.get("tp2"), signal.get("tp3"), signal.get("rr"), signal.get("score"),
                    signal.get("confidence"), signal.get("state", "PUBLISHED"), signal.get("current_price"),
                    signal.get("current_r"), signal.get("best_r", 0), signal.get("worst_r", 0),
                    signal.get("closed_at"), signal.get("final_result"), _json(metadata),
                ),
            )

    def get_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM signals WHERE signal_id = ?", (str(signal_id),)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        return result

    def list_signals(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM signals"
        params: tuple = ()
        if state:
            query += " WHERE state = ?"
            params = (state,)
        query += " ORDER BY published_at DESC"
        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            results.append(item)
        return results

    def record_signal_event(
        self,
        signal_id: str,
        event_type: str,
        price: Optional[float] = None,
        r_value: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
        event_at: Optional[str] = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO signal_events(signal_id, event_type, event_at, price, r_value, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(signal_id), str(event_type), event_at or utc_now_iso(), price, r_value, _json(payload or {})),
            )

    def list_signal_events(self, signal_id: str) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM signal_events WHERE signal_id = ? ORDER BY event_at ASC, id ASC",
                (str(signal_id),),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            results.append(item)
        return results

    def save_opportunity(self, opportunity: Dict[str, Any]) -> None:
        required = ("opportunity_id", "symbol", "lifecycle_state")
        missing = [key for key in required if not opportunity.get(key)]
        if missing:
            raise ValueError("Opportunité incomplète : " + ", ".join(missing))
        now = utc_now_iso()
        first_seen = str(opportunity.get("first_seen_at") or now)
        last_seen = str(opportunity.get("last_seen_at") or now)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO opportunities(opportunity_id, symbol, lifecycle_state, first_seen_at, last_seen_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(opportunity_id) DO UPDATE SET
                    symbol=excluded.symbol,
                    lifecycle_state=excluded.lifecycle_state,
                    last_seen_at=excluded.last_seen_at,
                    payload_json=excluded.payload_json
                """,
                (str(opportunity["opportunity_id"]), str(opportunity["symbol"]), str(opportunity["lifecycle_state"]), first_seen, last_seen, _json(opportunity.get("payload", {}))),
            )

    def list_opportunities(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM opportunities"
        params: tuple = ()
        if symbol:
            query += " WHERE symbol = ?"
            params = (str(symbol),)
        query += " ORDER BY last_seen_at DESC"
        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            results.append(item)
        return results

    def record_health(
        self,
        component: str,
        status: str,
        latency_ms: Optional[float] = None,
        message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO health_events(component, status, checked_at, latency_ms, message, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (component, status, utc_now_iso(), latency_ms, message, _json(payload or {})),
            )

    def close(self) -> None:
        """Compatibilité API : les connexions sont courtes et auto-fermées."""
        return None


_storage_singleton: Optional[SQLiteStorage] = None


def get_storage(db_path: Optional[str] = None) -> SQLiteStorage:
    global _storage_singleton
    if db_path is not None:
        return SQLiteStorage(db_path)
    if _storage_singleton is None:
        _storage_singleton = SQLiteStorage()
    return _storage_singleton
