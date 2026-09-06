from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class SignalStatus(str, Enum):
    ACTIVE = "ACTIVE"

    BE_RECOMMENDED = "BE_RECOMMENDED"
    BE_ACTIVE = "BE_ACTIVE"

    TP1_HIT = "TP1_HIT"
    TP_HIT = "TP_HIT"

    SL_HIT = "SL_HIT"

    INVALIDATED = "INVALIDATED"

    CLOSED = "CLOSED"


class MarketType(str, Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"


@dataclass(frozen=True)
class Candle:
    """
    Bougie OHLCV normalisée.
    """

    timestamp: datetime

    open: float
    high: float
    low: float
    close: float

    volume: float = 0.0

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low


@dataclass(frozen=True)
class TrendContext:
    """
    Contexte D1 + H4.
    """

    d1: Direction
    h4: Direction

    d1_strength: float = 0.0
    h4_strength: float = 0.0

    @property
    def aligned(self) -> bool:
        return (
            self.d1 != Direction.NEUTRAL
            and self.d1 == self.h4
        )

    @property
    def direction(self) -> Direction:
        if self.aligned:
            return self.d1

        return Direction.NEUTRAL


@dataclass(frozen=True)
class Zone:
    """
    Zone détectée sur H1/M15.
    """

    direction: Direction

    timeframe: str

    low: float
    high: float

    h1_strength: float
    m15_strength: float

    kind: str

    structure_confirmed: bool = False
    liquidity_nearby: bool = False
    order_block: bool = False
    fvg: bool = False

    created_at: Optional[datetime] = None

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2

    @property
    def width(self) -> float:
        return abs(self.high - self.low)

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass(frozen=True)
class Confirmation:
    """
    Confirmation M5.
    """

    direction: Direction

    retest: bool

    rejection: bool

    liquidity_sweep: bool

    micro_bos: bool

    candle_confirmation: bool

    @property
    def valid(self) -> bool:
        return (
            self.retest
            and self.rejection
            and self.micro_bos
            and self.candle_confirmation
        )


@dataclass(frozen=True)
class Signal:
    """
    Signal final généré par le moteur.
    """

    signal_id: str

    symbol: str

    market_type: MarketType

    direction: Direction

    score: float

    entry: float

    stop_loss: float

    take_profit: float

    rr: float

    risk_percent: float

    zone: Zone

    confirmation: Confirmation

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def risk_distance(self) -> float:
        return abs(
            self.entry - self.stop_loss
        )


@dataclass
class SignalState:
    """
    État dynamique d'un signal.

    Cette classe permet au bot de suivre le signal
    après son émission.
    """

    signal: Signal

    current_price: float

    status: SignalStatus = SignalStatus.ACTIVE

    current_r: float = 0.0

    best_r: float = 0.0

    worst_r: float = 0.0

    progress_to_tp_percent: float = 0.0

    distance_to_sl: float = 0.0

    distance_to_tp: float = 0.0

    be_price: Optional[float] = None

    last_update: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_profitable(self) -> bool:
        return self.current_r > 0

    @property
    def is_in_loss(self) -> bool:
        return self.current_r < 0