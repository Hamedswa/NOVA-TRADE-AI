"""
NOVA TRADE AI
core/models.py

MODÈLES CENTRAUX DU SYSTÈME.

Architecture :

    Tendance
        ↓
    Zone clé
        ↓
    Cassure
        ↓
    Retest
        ↓
    Confirmation
        ↓
    Entrée
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ============================================================
# DIRECTION
# ============================================================

class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


# ============================================================
# STATUT SIGNAL
# ============================================================

class SignalStatus(str, Enum):
    ACTIVE = "ACTIVE"

    BE_RECOMMENDED = "BE_RECOMMENDED"
    BE_ACTIVE = "BE_ACTIVE"

    TP1_HIT = "TP1_HIT"
    TP_HIT = "TP_HIT"

    SL_HIT = "SL_HIT"

    INVALIDATED = "INVALIDATED"

    CLOSED = "CLOSED"


# ============================================================
# TYPE DE MARCHÉ
# ============================================================

class MarketType(str, Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"


# ============================================================
# BOUGIE
# ============================================================

@dataclass(frozen=True)
class Candle:

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
        return abs(
            self.close - self.open
        )

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return (
            self.high
            - max(
                self.open,
                self.close,
            )
        )

    @property
    def lower_wick(self) -> float:
        return (
            min(
                self.open,
                self.close,
            )
            - self.low
        )

    @property
    def body_ratio(self) -> float:

        if self.range <= 0:
            return 0.0

        return self.body / self.range


# ============================================================
# CONTEXTE DE TENDANCE
# ============================================================

@dataclass(frozen=True)
class TrendContext:

    """
    H4 = tendance globale.

    H1 + M15 sont validés séparément
    dans le pipeline.
    """

    h4: Direction

    h4_strength: float = 0.0

    @property
    def aligned(self) -> bool:

        return (
            self.h4
            != Direction.NEUTRAL
        )

    @property
    def direction(self) -> Direction:

        if self.aligned:
            return self.h4

        return Direction.NEUTRAL


# ============================================================
# ZONE CLÉ
# ============================================================

@dataclass(frozen=True)
class Zone:

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

    # ========================================================
    # NOUVELLE VALIDATION PRICE ACTION
    # ========================================================

    level_type: str = "NONE"

    key_level: float = 0.0

    breakout_confirmed: bool = False

    breakout_direction: Direction = Direction.NEUTRAL

    retest_confirmed: bool = False

    rejection_confirmed: bool = False

    candle_confirmation: bool = False

    entry_valid: bool = False

    entry_distance: float = 0.0

    # ========================================================
    # PROPRIÉTÉS
    # ========================================================

    @property
    def midpoint(self) -> float:

        return (
            self.low
            + self.high
        ) / 2

    @property
    def width(self) -> float:

        return abs(
            self.high
            - self.low
        )

    def contains(
        self,
        price: float,
    ) -> bool:

        return (
            self.low
            <= price
            <= self.high
        )

    @property
    def is_valid_setup(self) -> bool:

        return (
            self.level_type
            in {
                "SUPPORT",
                "RESISTANCE",
            }
            and self.key_level > 0
            and self.breakout_confirmed
            and self.retest_confirmed
            and self.rejection_confirmed
            and self.candle_confirmation
            and self.entry_valid
        )


# ============================================================
# CONFIRMATION
# ============================================================

@dataclass(frozen=True)
class Confirmation:

    """
    Confirmation M5.

    M5 reste secondaire.

    La validation principale du setup
    est désormais portée par Zone.
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
            and self.candle_confirmation
            and (
                self.micro_bos
                or self.liquidity_sweep
            )
        )


# ============================================================
# SIGNAL
# ============================================================

@dataclass(frozen=True)
class Signal:

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
        default_factory=lambda:
        datetime.now(timezone.utc)
    )

    @property
    def risk_distance(self) -> float:

        return abs(
            self.entry
            - self.stop_loss
        )


# ============================================================
# ÉTAT SIGNAL
# ============================================================

@dataclass
class SignalState:

    signal: Signal

    current_price: float

    status: SignalStatus = (
        SignalStatus.ACTIVE
    )

    current_r: float = 0.0

    best_r: float = 0.0

    worst_r: float = 0.0

    progress_to_tp_percent: float = 0.0

    distance_to_sl: float = 0.0

    distance_to_tp: float = 0.0

    be_price: Optional[float] = None

    last_update: datetime = field(
        default_factory=lambda:
        datetime.now(timezone.utc)
    )

    @property
    def is_profitable(self) -> bool:

        return self.current_r > 0

    @property
    def is_in_loss(self) -> bool:

        return self.current_r < 0