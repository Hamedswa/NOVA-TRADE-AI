"""
NOVA TRADE AI - ENGINE 2
MARKET RADAR

Rôle :
    Surveiller en permanence les informations disponibles sur le marché
    et détecter les changements, accélérations, anomalies et zones
    susceptibles de devenir intéressantes.

IMPORTANT :
    Le Radar ne décide jamais BUY / SELL.
    Il ne bloque jamais une opportunité.
    Il ne remplace pas moteur2_intelligence.py.
    Il ne remplace pas moteur2_decision.py.

Architecture :

    BiQuote / Market Data
            ↓
       MARKET RADAR
            ↓
    événements détectés
    changements de régime
    mouvements rapides
    accélérations
    volatilité
    pression
    changements de direction
    zones approchées
            ↓
    moteur2_intelligence.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


ENGINE_NAME = "NOVA TRADE AI - ENGINE 2"
MODULE_NAME = "MARKET_RADAR"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


@dataclass
class RadarEvent:
    symbol: str
    event_type: str
    timeframe: str = ""
    direction: str = "NEUTRAL"
    strength: float = 0.0
    price: Optional[float] = None
    previous_value: Any = None
    current_value: Any = None
    description: str = ""
    timestamp: str = field(default_factory=_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_type": self.event_type,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strength": self.strength,
            "price": self.price,
            "previous_value": self.previous_value,
            "current_value": self.current_value,
            "description": self.description,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class Moteur2Radar:
    """
    Radar de surveillance du marché.

    Le Radar cherche ce qui CHANGE.

    Il ne cherche pas uniquement à confirmer une idée existante.

    Il peut donc détecter :
        - accélération
        - ralentissement
        - changement de direction
        - changement de volatilité
        - pression acheteurs/vendeurs
        - rupture de contexte
        - approche d'une zone
        - mouvement inhabituel
        - divergence entre timeframes
        - nouveau contexte exploitable
    """

    def __init__(
        self,
        movement_threshold: float = 0.30,
        volatility_threshold: float = 1.50,
        pressure_threshold: float = 20.0,
    ) -> None:

        self.engine_name = ENGINE_NAME
        self.module_name = MODULE_NAME

        self.movement_threshold = float(movement_threshold)
        self.volatility_threshold = float(volatility_threshold)
        self.pressure_threshold = float(pressure_threshold)

        self.scan_count = 0
        self.events_count = 0

        self._previous_snapshots: Dict[str, Dict[str, Any]] = {}

        self.last_events: List[RadarEvent] = []

    # ------------------------------------------------------------------
    # API PRINCIPALE
    # ------------------------------------------------------------------

    def surveiller(
        self,
        symbol: str,
        market_data: Optional[Dict[str, Any]] = None,
        zones: Optional[List[Dict[str, Any]]] = None,
    ) -> List[RadarEvent]:

        symbol = _text(symbol)

        market_data = (
            market_data
            if isinstance(market_data, dict)
            else {}
        )

        zones = zones if isinstance(zones, list) else []

        events: List[RadarEvent] = []

        previous = self._previous_snapshots.get(
            symbol,
            {},
        )

        current = self._build_snapshot(
            market_data
        )

        # --------------------------------------------------------------
        # 1. MOUVEMENT
        # --------------------------------------------------------------

        events.extend(
            self._detect_price_movement(
                symbol,
                previous,
                current,
            )
        )

        # --------------------------------------------------------------
        # 2. CHANGEMENT DE DIRECTION
        # --------------------------------------------------------------

        events.extend(
            self._detect_direction_change(
                symbol,
                previous,
                current,
            )
        )

        # --------------------------------------------------------------
        # 3. MOMENTUM
        # --------------------------------------------------------------

        events.extend(
            self._detect_momentum_change(
                symbol,
                previous,
                current,
            )
        )

        # --------------------------------------------------------------
        # 4. VOLATILITÉ
        # --------------------------------------------------------------

        events.extend(
            self._detect_volatility_change(
                symbol,
                previous,
                current,
            )
        )

        # --------------------------------------------------------------
        # 5. PRESSION
        # --------------------------------------------------------------

        events.extend(
            self._detect_pressure_change(
                symbol,
                previous,
                current,
            )
        )

        # --------------------------------------------------------------
        # 6. APPROCHE D'UNE ZONE
        # --------------------------------------------------------------

        events.extend(
            self._detect_zone_proximity(
                symbol,
                current,
                zones,
            )
        )

        # --------------------------------------------------------------
        # 7. DIVERGENCE MULTI-TIMEFRAME
        # --------------------------------------------------------------

        events.extend(
            self._detect_timeframe_divergence(
                symbol,
                current,
            )
        )

        # --------------------------------------------------------------
        # 8. ANOMALIE
        # --------------------------------------------------------------

        events.extend(
            self._detect_anomaly(
                symbol,
                previous,
                current,
            )
        )

        # --------------------------------------------------------------
        # SAUVEGARDE DU SNAPSHOT
        # --------------------------------------------------------------

        self._previous_snapshots[symbol] = current

        self.scan_count += 1
        self.events_count += len(events)

        self.last_events = events

        return events

    # Alias
    analyser = surveiller
    scan = surveiller

    # ------------------------------------------------------------------
    # SNAPSHOT
    # ------------------------------------------------------------------

    def _build_snapshot(
        self,
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:

        snapshot: Dict[str, Any] = {
            "timestamp": _now_iso(),
            "price": _float(
                market_data.get("price")
                or market_data.get("last")
                or market_data.get("close")
            ),
            "direction": self._extract_direction(
                market_data
            ),
            "momentum": _float(
                market_data.get("momentum")
            ),
            "volatility": _float(
                market_data.get("volatility")
                or market_data.get("volatility_ratio")
                or market_data.get("atr_ratio")
            ),
            "buy_pressure": _float(
                market_data.get("buy_pressure"),
                0.0,
            ),
            "sell_pressure": _float(
                market_data.get("sell_pressure"),
                0.0,
            ),
            "timeframes": {},
        }

        timeframes = market_data.get("timeframes")

        if isinstance(timeframes, dict):

            for timeframe, data in timeframes.items():

                if not isinstance(data, dict):
                    continue

                snapshot["timeframes"][
                    _text(timeframe)
                ] = {
                    "direction": self._extract_direction(data),
                    "price": _float(
                        data.get("price")
                        or data.get("close")
                    ),
                    "momentum": _float(
                        data.get("momentum")
                    ),
                    "volatility": _float(
                        data.get("volatility")
                        or data.get("volatility_ratio")
                        or data.get("atr_ratio")
                    ),
                    "buy_pressure": _float(
                        data.get("buy_pressure"),
                        0.0,
                    ),
                    "sell_pressure": _float(
                        data.get("sell_pressure"),
                        0.0,
                    ),
                }

        return snapshot

    # ------------------------------------------------------------------
    # PRICE MOVEMENT
    # ------------------------------------------------------------------

    def _detect_price_movement(
        self,
        symbol: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[RadarEvent]:

        events: List[RadarEvent] = []

        old_price = _float(
            previous.get("price")
        )

        new_price = _float(
            current.get("price")
        )

        if old_price is None or new_price is None:
            return events

        if old_price == 0:
            return events

        change_pct = (
            (new_price - old_price)
            / abs(old_price)
        ) * 100.0

        if abs(change_pct) < self.movement_threshold:
            return events

        direction = (
            "BUY"
            if change_pct > 0
            else "SELL"
        )

        strength = min(
            100.0,
            abs(change_pct) * 25.0,
        )

        events.append(
            RadarEvent(
                symbol=symbol,
                event_type="PRICE_ACCELERATION",
                direction=direction,
                strength=round(strength, 2),
                price=new_price,
                previous_value=old_price,
                current_value=new_price,
                description=(
                    f"Mouvement significatif détecté : "
                    f"{change_pct:.3f}%."
                ),
            )
        )

        return events

    # ------------------------------------------------------------------
    # DIRECTION
    # ------------------------------------------------------------------

    def _detect_direction_change(
        self,
        symbol: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[RadarEvent]:

        old_direction = _text(
            previous.get("direction")
        )

        new_direction = _text(
            current.get("direction")
        )

        if not old_direction or not new_direction:
            return []

        if old_direction == new_direction:
            return []

        if new_direction not in ("BUY", "SELL"):
            return []

        return [
            RadarEvent(
                symbol=symbol,
                event_type="DIRECTION_CHANGE",
                direction=new_direction,
                strength=75.0,
                price=current.get("price"),
                previous_value=old_direction,
                current_value=new_direction,
                description=(
                    f"Changement de direction détecté : "
                    f"{old_direction} → {new_direction}."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # MOMENTUM
    # ------------------------------------------------------------------

    def _detect_momentum_change(
        self,
        symbol: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[RadarEvent]:

        old = _float(
            previous.get("momentum")
        )

        new = _float(
            current.get("momentum")
        )

        if old is None or new is None:
            return []

        delta = new - old

        if abs(delta) < 0.20:
            return []

        direction = (
            "BUY"
            if delta > 0
            else "SELL"
        )

        return [
            RadarEvent(
                symbol=symbol,
                event_type="MOMENTUM_CHANGE",
                direction=direction,
                strength=min(
                    100.0,
                    abs(delta) * 50.0,
                ),
                previous_value=old,
                current_value=new,
                description=(
                    "Variation significative du momentum."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # VOLATILITÉ
    # ------------------------------------------------------------------

    def _detect_volatility_change(
        self,
        symbol: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[RadarEvent]:

        old = _float(
            previous.get("volatility")
        )

        new = _float(
            current.get("volatility")
        )

        if old is None or new is None:
            return []

        if old == 0:
            return []

        ratio = new / old

        if ratio >= self.volatility_threshold:

            return [
                RadarEvent(
                    symbol=symbol,
                    event_type="VOLATILITY_EXPANSION",
                    strength=min(
                        100.0,
                        ratio * 30.0,
                    ),
                    price=current.get("price"),
                    previous_value=old,
                    current_value=new,
                    description=(
                        "Expansion importante de la volatilité."
                    ),
                )
            ]

        if ratio <= 1.0 / self.volatility_threshold:

            return [
                RadarEvent(
                    symbol=symbol,
                    event_type="VOLATILITY_CONTRACTION",
                    strength=60.0,
                    price=current.get("price"),
                    previous_value=old,
                    current_value=new,
                    description=(
                        "Contraction importante de la volatilité."
                    ),
                )
            ]

        return []

    # ------------------------------------------------------------------
    # PRESSION
    # ------------------------------------------------------------------

    def _detect_pressure_change(
        self,
        symbol: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[RadarEvent]:

        old_buy = _float(
            previous.get("buy_pressure"),
            0.0,
        ) or 0.0

        old_sell = _float(
            previous.get("sell_pressure"),
            0.0,
        ) or 0.0

        new_buy = _float(
            current.get("buy_pressure"),
            0.0,
        ) or 0.0

        new_sell = _float(
            current.get("sell_pressure"),
            0.0,
        ) or 0.0

        old_balance = old_buy - old_sell
        new_balance = new_buy - new_sell

        delta = new_balance - old_balance

        if abs(delta) < self.pressure_threshold:
            return []

        direction = (
            "BUY"
            if delta > 0
            else "SELL"
        )

        return [
            RadarEvent(
                symbol=symbol,
                event_type="PRESSURE_SHIFT",
                direction=direction,
                strength=min(
                    100.0,
                    abs(delta),
                ),
                price=current.get("price"),
                previous_value=old_balance,
                current_value=new_balance,
                description=(
                    "Changement significatif de la pression "
                    "acheteurs/vendeurs."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # ZONES
    # ------------------------------------------------------------------

    def _detect_zone_proximity(
        self,
        symbol: str,
        current: Dict[str, Any],
        zones: List[Dict[str, Any]],
    ) -> List[RadarEvent]:

        price = _float(
            current.get("price")
        )

        if price is None:
            return []

        events: List[RadarEvent] = []

        for zone in zones:

            if not isinstance(zone, dict):
                continue

            low = _float(
                zone.get("low")
                or zone.get("lower")
                or zone.get("min")
            )

            high = _float(
                zone.get("high")
                or zone.get("upper")
                or zone.get("max")
            )

            zone_price = _float(
                zone.get("price")
                or zone.get("level")
            )

            if low is not None and high is not None:

                if low <= price <= high:

                    events.append(
                        RadarEvent(
                            symbol=symbol,
                            event_type="ZONE_INTERACTION",
                            strength=80.0,
                            price=price,
                            current_value=zone,
                            description=(
                                "Le prix se trouve dans une zone "
                                "importante détectée."
                            ),
                        )
                    )

            elif zone_price is not None:

                distance = abs(
                    price - zone_price
                )

                reference = max(
                    abs(price),
                    1e-9,
                )

                distance_pct = (
                    distance / reference
                ) * 100.0

                if distance_pct <= 0.20:

                    events.append(
                        RadarEvent(
                            symbol=symbol,
                            event_type="ZONE_APPROACH",
                            strength=70.0,
                            price=price,
                            current_value=zone,
                            description=(
                                "Le prix approche d'une "
                                "zone importante."
                            ),
                        )
                    )

        return events

    # ------------------------------------------------------------------
    # DIVERGENCE MULTI-TIMEFRAME
    # ------------------------------------------------------------------

    def _detect_timeframe_divergence(
        self,
        symbol: str,
        current: Dict[str, Any],
    ) -> List[RadarEvent]:

        timeframes = current.get(
            "timeframes",
            {},
        )

        if not isinstance(timeframes, dict):
            return []

        directions = []

        for timeframe in (
            "H4",
            "H1",
            "M15",
            "M5",
            "M1",
        ):

            data = timeframes.get(timeframe)

            if not isinstance(data, dict):
                continue

            direction = _text(
                data.get("direction")
            )

            if direction in ("BUY", "SELL"):
                directions.append(
                    direction
                )

        if len(directions) < 2:
            return []

        buy_count = directions.count("BUY")
        sell_count = directions.count("SELL")

        if buy_count == 0 or sell_count == 0:
            return []

        return [
            RadarEvent(
                symbol=symbol,
                event_type="TIMEFRAME_DIVERGENCE",
                strength=65.0,
                price=current.get("price"),
                previous_value=None,
                current_value={
                    "BUY": buy_count,
                    "SELL": sell_count,
                },
                description=(
                    "Les timeframes ne présentent pas "
                    "une lecture directionnelle uniforme."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # ANOMALIE
    # ------------------------------------------------------------------

    def _detect_anomaly(
        self,
        symbol: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[RadarEvent]:

        old_price = _float(
            previous.get("price")
        )

        new_price = _float(
            current.get("price")
        )

        volatility = _float(
            current.get("volatility")
        )

        if (
            old_price is None
            or new_price is None
            or volatility is None
            or old_price == 0
        ):
            return []

        change_pct = abs(
            (new_price - old_price)
            / old_price
        ) * 100.0

        # Mouvement inhabituel par rapport à la volatilité observée.
        if volatility > 0 and change_pct > (
            volatility * 2.0
        ):

            direction = (
                "BUY"
                if new_price > old_price
                else "SELL"
            )

            return [
                RadarEvent(
                    symbol=symbol,
                    event_type="MARKET_ANOMALY",
                    direction=direction,
                    strength=90.0,
                    price=new_price,
                    previous_value=old_price,
                    current_value=new_price,
                    description=(
                        "Mouvement inhabituel détecté "
                        "par rapport à la volatilité."
                    ),
                )
            ]

        return []

    # ------------------------------------------------------------------
    # DIRECTION
    # ------------------------------------------------------------------

    def _extract_direction(
        self,
        data: Dict[str, Any],
    ) -> str:

        for key in (
            "direction",
            "bias",
            "trend",
            "signal",
            "side",
        ):

            value = _text(
                data.get(key)
            )

            if value in (
                "BUY",
                "LONG",
                "BULLISH",
                "UP",
            ):
                return "BUY"

            if value in (
                "SELL",
                "SHORT",
                "BEARISH",
                "DOWN",
            ):
                return "SELL"

        return "NEUTRAL"

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:

        return {
            "engine": self.engine_name,
            "module": self.module_name,
            "scan_count": self.scan_count,
            "events_count": self.events_count,
            "symbols_tracked": len(
                self._previous_snapshots
            ),

            "decision_owner": (
                "moteur2_decision.py"
            ),

            "makes_trade_decision": False,
            "blocks_trade": False,

            "adaptive_monitoring": True,
            "checklist_mode": False,

            "multiple_events_allowed": True,
            "signal_quota": None,

            "last_events": [
                event.to_dict()
                for event in self.last_events
            ],
        }


# ---------------------------------------------------------------------------
# ALIAS
# ---------------------------------------------------------------------------

MarketRadar = Moteur2Radar


# ---------------------------------------------------------------------------
# TEST LOCAL
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    radar = Moteur2Radar()

    first_scan = radar.surveiller(
        "XAUUSD",
        {
            "price": 3400.0,
            "direction": "BUY",
            "momentum": 0.5,
            "volatility": 1.0,
            "buy_pressure": 60,
            "sell_pressure": 30,
            "timeframes": {
                "H4": {"direction": "BUY"},
                "H1": {"direction": "BUY"},
                "M15": {"direction": "BUY"},
            },
        },
    )

    second_scan = radar.surveiller(
        "XAUUSD",
        {
            "price": 3415.0,
            "direction": "BUY",
            "momentum": 1.2,
            "volatility": 2.0,
            "buy_pressure": 95,
            "sell_pressure": 25,
            "timeframes": {
                "H4": {"direction": "BUY"},
                "H1": {"direction": "BUY"},
                "M15": {"direction": "SELL"},
            },
        },
    )

    print("=" * 70)
    print("NOVA TRADE AI - MARKET RADAR TEST")
    print("=" * 70)

    for event in second_scan:
        print(
            event.event_type,
            "|",
            event.direction,
            "|",
            event.strength,
            "|",
            event.description,
        )

    print("\nSTATUS")
    print(radar.get_status())