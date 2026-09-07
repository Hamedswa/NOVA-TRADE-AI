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
# SIGNAL STATUS
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
# MARKET TYPE
# ============================================================
class MarketType(str, Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
# ============================================================
# CANDLE
# ============================================================
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
# ============================================================
# TREND CONTEXT
# ============================================================
@dataclass(frozen=True)
class TrendContext:
    """
    Contexte directionnel multi-timeframe.
    Architecture principale :
        D1 → H4 → H1 → M15
    Les quatre timeframes sont utilisés pour déterminer
    la direction principale du setup.
    M5 n'est PAS inclus ici car il constitue uniquement
    une confirmation d'entrée secondaire.
    """
    d1: Direction
    h4: Direction
    h1: Direction = Direction.NEUTRAL
    m15: Direction = Direction.NEUTRAL
    d1_strength: float = 0.0
    h4_strength: float = 0.0
    h1_strength: float = 0.0
    m15_strength: float = 0.0
    @property
    def primary_aligned(self) -> bool:
        """
        True uniquement si D1/H4/H1/M15 sont parfaitement
        alignés dans la même direction.
        Exemple valide :
            BUY / BUY / BUY / BUY
        ou :
            SELL / SELL / SELL / SELL
        """
        directions = (
            self.d1,
            self.h4,
            self.h1,
            self.m15,
        )
        if any(
            direction == Direction.NEUTRAL
            for direction in directions
        ):
            return False
        return (
            self.d1
            == self.h4
            == self.h1
            == self.m15
        )
    @property
    def aligned(self) -> bool:
        """
        Alias de compatibilité.
        L'ancien moteur utilisait .aligned.
        """
        return self.primary_aligned
    @property
    def direction(self) -> Direction:
        """
        Direction principale du setup.
        Retourne BUY ou SELL uniquement lorsque les quatre
        timeframes principaux sont alignés.
        Sinon NEUTRAL.
        """
        if not self.primary_aligned:
            return Direction.NEUTRAL
        return self.d1
    @property
    def alignment_count(self) -> int:
        """
        Nombre de timeframes principaux partageant la direction
        dominante non-neutre.
        Utile pour le scoring et le diagnostic.
        """
        directions = (
            self.d1,
            self.h4,
            self.h1,
            self.m15,
        )
        non_neutral = [
            direction
            for direction in directions
            if direction != Direction.NEUTRAL
        ]
        if not non_neutral:
            return 0
        dominant = non_neutral[0]
        return sum(
            direction == dominant
            for direction in non_neutral
        )
# ============================================================
# ZONE
# ============================================================
@dataclass(frozen=True)
class Zone:
    """
    Zone détectée principalement sur H1/M15.
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
# ============================================================
# M5 CONFIRMATION
# ============================================================
@dataclass(frozen=True)
class Confirmation:
    """
    Confirmation d'entrée M5.
    IMPORTANT :
    M5 est secondaire.
    Une confirmation M5 invalide ou absente ne doit pas
    annuler un setup lorsque D1/H4/H1/M15 sont parfaitement
    alignés.
    """
    direction: Direction
    retest: bool
    rejection: bool
    liquidity_sweep: bool
    micro_bos: bool
    candle_confirmation: bool
    @property
    def valid(self) -> bool:
        """
        Validation complète d'une confirmation M5.
        Plusieurs configurations sont acceptées :
        1. Micro BOS + bougie
        2. Liquidity Sweep + rejet + bougie
        3. Retest + rejet + bougie
        """
        if (
            self.micro_bos
            and self.candle_confirmation
        ):
            return True
        if (
            self.liquidity_sweep
            and self.rejection
            and self.candle_confirmation
        ):
            return True
        if (
            self.retest
            and self.rejection
            and self.candle_confirmation
        ):
            return True
        return False
# ============================================================
# SIGNAL
# ============================================================
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
# ============================================================
# SIGNAL STATE
# ============================================================
@dataclass
class SignalState:
    """
    État dynamique d'un signal.
    Permet au bot de suivre le signal après son émission.
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