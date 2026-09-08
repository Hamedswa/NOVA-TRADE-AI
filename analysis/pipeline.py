"""
NOVA TRADE AI
analysis/pipeline.py

PIPELINE PRINCIPAL D'ANALYSE

Architecture :

    DATA
      │
      ├── H4  → tendance globale
      ├── H1  → structure / niveaux
      ├── M15 → contexte / zone
      └── M5  → entrée sniper
              │
              ▼
        ALIGNEMENT H4/H1/M15
              │
              ▼
          ZONE CLÉ
              │
              ▼
           CASSURE
              │
              ▼
           RETEST
              │
              ▼
         REJECTION
              │
              ▼
       BOUGIE CONFIRMÉE
              │
              ▼
        ENTRÉE PRÉCISE
              │
              ▼
          SL / TP / RR
              │
              ▼
           SCORE
              │
              ▼
       FILTRE NEWS / MARCHÉ
              │
              ▼
           SIGNAL

IMPORTANT :
- H4 + H1 + M15 sont la validation principale.
- M5 est secondaire / non bloquante.
- M5 peut améliorer l'entrée en mode sniper.
- Aucun D1.
- Aucun signal ne doit être forcé.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from config import CONFIG

from core.models import (
    Candle,
    Confirmation,
    Direction,
    MarketType,
    Signal,
    TrendContext,
    Zone,
)

from risk.risk_manager import calculate_rr

from signals.signal_engine import (
    SignalEngine,
    build_signal,
)

try:
    from market_data import market_data
except Exception:
    market_data = None

try:
    from economic_calendar import economic_filter
except Exception:
    economic_filter = None

try:
    from market_hours import is_market_open
except Exception:
    is_market_open = None


logger = logging.getLogger("NOVA_TRADE_AI.pipeline")


# ============================================================
# CONSTANTES
# ============================================================

MIN_CANDLES = 30

H4_MIN_CANDLES = 40
H1_MIN_CANDLES = 40
M15_MIN_CANDLES = 60
M5_MIN_CANDLES = 50

ATR_PERIOD = 14

ENTRY_MAX_ATR = 0.35
LEVEL_PROXIMITY_ATR = 0.50

BREAKOUT_BODY_RATIO = 0.45
CONFIRMATION_BODY_RATIO = 0.50

SWING_LOOKBACK = 2

MAX_LEVELS = 12


# ============================================================
# OUTILS GÉNÉRAUX
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except Exception:
        return default


def _normalize_direction(value: Any) -> Direction:
    if isinstance(value, Direction):
        return value

    if value is None:
        return Direction.NEUTRAL

    text = str(value).upper().strip()

    if text in {"BUY", "LONG", "BULLISH", "UP"}:
        return Direction.BUY

    if text in {"SELL", "SHORT", "BEARISH", "DOWN"}:
        return Direction.SELL

    return Direction.NEUTRAL


def _direction_text(direction: Any) -> str:
    direction = _normalize_direction(direction)
    return direction.value


def _market_type(symbol: str) -> MarketType:
    symbol = symbol.upper()

    if symbol.endswith("/USD") and symbol.split("/")[0] in {
        "BTC",
        "ETH",
        "SOL",
        "BNB",
        "XRP",
    }:
        return MarketType.CRYPTO

    return MarketType.FOREX


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# EXTRACTION DES CHANDELIERS
# ============================================================

def _extract_candles(data: Any) -> list[Candle]:
    """
    Convertit différents formats retournés par market_data
    en liste uniforme de Candle.
    """

    if data is None:
        return []

    # --------------------------------------------------------
    # Si l'objet possède directement une propriété candles
    # --------------------------------------------------------

    if hasattr(data, "candles"):
        try:
            nested = data.candles
            if nested is not data:
                return _extract_candles(nested)
        except Exception:
            pass

    # --------------------------------------------------------
    # Dict contenant data / candles / values / results
    # --------------------------------------------------------

    if isinstance(data, dict):

        for key in (
            "candles",
            "data",
            "values",
            "results",
            "result",
        ):
            if key in data:
                try:
                    extracted = _extract_candles(data[key])
                    if extracted:
                        return extracted
                except Exception:
                    pass

        # Un chandelier unique
        if any(
            key in data
            for key in (
                "open",
                "o",
            )
        ):
            data = [data]
        else:
            return []

    # --------------------------------------------------------
    # Objet iterable
    # --------------------------------------------------------

    if isinstance(data, (str, bytes)):
        return []

    try:
        rows = list(data)
    except Exception:
        rows = []

    candles: list[Candle] = []

    for row in rows:

        try:
            if isinstance(row, dict):

                timestamp = (
                    row.get("timestamp")
                    or row.get("datetime")
                    or row.get("date")
                    or row.get("time")
                )

                open_price = (
                    row.get("open")
                    if row.get("open") is not None
                    else row.get("o")
                )

                high_price = (
                    row.get("high")
                    if row.get("high") is not None
                    else row.get("h")
                )

                low_price = (
                    row.get("low")
                    if row.get("low") is not None
                    else row.get("l")
                )

                close_price = (
                    row.get("close")
                    if row.get("close") is not None
                    else row.get("c")
                )

                volume = (
                    row.get("volume")
                    if row.get("volume") is not None
                    else row.get("v", 0.0)
                )

            else:

                timestamp = (
                    getattr(row, "timestamp", None)
                    or getattr(row, "datetime", None)
                    or getattr(row, "date", None)
                    or getattr(row, "time", None)
                )

                open_price = (
                    getattr(row, "open", None)
                    or getattr(row, "o", None)
                )

                high_price = (
                    getattr(row, "high", None)
                    or getattr(row, "h", None)
                )

                low_price = (
                    getattr(row, "low", None)
                    or getattr(row, "l", None)
                )

                close_price = (
                    getattr(row, "close", None)
                    or getattr(row, "c", None)
                )

                volume = (
                    getattr(row, "volume", None)
                    or getattr(row, "v", 0.0)
                )

            if timestamp is None:
                continue

            if isinstance(timestamp, str):
                timestamp_text = timestamp.strip()

                if timestamp_text.endswith("Z"):
                    timestamp_text = timestamp_text[:-1] + "+00:00"

                try:
                    timestamp = datetime.fromisoformat(timestamp_text)
                except Exception:
                    timestamp = _now_utc()

            if not isinstance(timestamp, datetime):
                timestamp = _now_utc()

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            candle = Candle(
                timestamp=timestamp,
                open=_safe_float(open_price),
                high=_safe_float(high_price),
                low=_safe_float(low_price),
                close=_safe_float(close_price),
                volume=_safe_float(volume),
            )

            if (
                candle.high > 0
                and candle.low > 0
                and candle.close > 0
                and candle.high >= candle.low
            ):
                candles.append(candle)

        except Exception as exc:
            logger.debug(
                "Impossible de convertir un chandelier : %s",
                exc,
            )

    candles.sort(key=lambda candle: candle.timestamp)

    return candles


# ============================================================
# VALIDATION DES DONNÉES
# ============================================================

def _validate_candles(
    symbol: str,
    timeframe: str,
    candles: list[Candle],
    minimum: int,
) -> bool:

    if not candles:
        logger.error(
            "DATA %s %s : 0 chandelier",
            symbol,
            timeframe,
        )
        return False

    if len(candles) < minimum:
        logger.error(
            "DATA %s %s : %d chandeliers seulement "
            "(minimum=%d)",
            symbol,
            timeframe,
            len(candles),
            minimum,
        )
        return False

    invalid = 0

    for candle in candles[-minimum:]:
        if (
            candle.open <= 0
            or candle.high <= 0
            or candle.low <= 0
            or candle.close <= 0
            or candle.high < candle.low
        ):
            invalid += 1

    if invalid:
        logger.error(
            "DATA %s %s : %d chandeliers invalides",
            symbol,
            timeframe,
            invalid,
        )
        return False

    logger.info(
        "DATA %s %s : OK (%d chandeliers)",
        symbol,
        timeframe,
        len(candles),
    )

    return True


# ============================================================
# ATR
# ============================================================

def _atr(candles: list[Candle], period: int = ATR_PERIOD) -> float:

    if len(candles) < period + 1:
        return 0.0

    true_ranges: list[float] = []

    for index in range(1, len(candles)):

        current = candles[index]
        previous = candles[index - 1]

        tr = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )

        true_ranges.append(max(0.0, tr))

    if len(true_ranges) < period:
        return 0.0

    return sum(true_ranges[-period:]) / period


# ============================================================
# SWINGS
# ============================================================

def _swing_highs(
    candles: list[Candle],
    lookback: int = SWING_LOOKBACK,
) -> list[float]:

    result: list[float] = []

    if len(candles) < (lookback * 2 + 1):
        return result

    for index in range(
        lookback,
        len(candles) - lookback,
    ):

        value = candles[index].high

        left = candles[
            index - lookback:index
        ]

        right = candles[
            index + 1:index + lookback + 1
        ]

        if all(value >= candle.high for candle in left) and all(
            value >= candle.high for candle in right
        ):
            result.append(value)

    return result


def _swing_lows(
    candles: list[Candle],
    lookback: int = SWING_LOOKBACK,
) -> list[float]:

    result: list[float] = []

    if len(candles) < (lookback * 2 + 1):
        return result

    for index in range(
        lookback,
        len(candles) - lookback,
    ):

        value = candles[index].low

        left = candles[
            index - lookback:index
        ]

        right = candles[
            index + 1:index + lookback + 1
        ]

        if all(value <= candle.low for candle in left) and all(
            value <= candle.low for candle in right
        ):
            result.append(value)

    return result


# ============================================================
# DIRECTION STRUCTURELLE
# ============================================================

def _structure_direction(
    candles: list[Candle],
) -> Direction:

    if len(candles) < 10:
        return Direction.NEUTRAL

    highs = _swing_highs(candles)
    lows = _swing_lows(candles)

    bullish_points = 0
    bearish_points = 0

    # --------------------------------------------------------
    # Structure récente
    # --------------------------------------------------------

    if len(highs) >= 2:

        if highs[-1] > highs[-2]:
            bullish_points += 1

        elif highs[-1] < highs[-2]:
            bearish_points += 1

    if len(lows) >= 2:

        if lows[-1] > lows[-2]:
            bullish_points += 1

        elif lows[-1] < lows[-2]:
            bearish_points += 1

    # --------------------------------------------------------
    # Deuxième lecture sur les derniers swings
    # --------------------------------------------------------

    if len(highs) >= 3:

        if highs[-1] > highs[-2] > highs[-3]:
            bullish_points += 1

        elif highs[-1] < highs[-2] < highs[-3]:
            bearish_points += 1

    if len(lows) >= 3:

        if lows[-1] > lows[-2] > lows[-3]:
            bullish_points += 1

        elif lows[-1] < lows[-2] < lows[-3]:
            bearish_points += 1

    if bullish_points >= 2 and bullish_points > bearish_points:
        return Direction.BUY

    if bearish_points >= 2 and bearish_points > bullish_points:
        return Direction.SELL

    # --------------------------------------------------------
    # Fallback momentum structurel
    # --------------------------------------------------------

    recent = candles[-20:]

    if len(recent) >= 10:

        first_close = recent[0].close
        last_close = recent[-1].close

        atr = _atr(candles)

        if atr > 0:

            movement = last_close - first_close

            if movement > atr * 0.5:
                return Direction.BUY

            if movement < -atr * 0.5:
                return Direction.SELL

    return Direction.NEUTRAL


# ============================================================
# ALIGNEMENT PRINCIPAL
# ============================================================

def is_primary_alignment_valid(
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> bool:

    h4 = _normalize_direction(h4)
    h1 = _normalize_direction(h1)
    m15 = _normalize_direction(m15)

    if (
        h4 == Direction.NEUTRAL
        or h1 == Direction.NEUTRAL
        or m15 == Direction.NEUTRAL
    ):
        return False

    return h4 == h1 == m15


def get_primary_direction(
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> Direction:

    if not is_primary_alignment_valid(
        h4,
        h1,
        m15,
    ):
        return Direction.NEUTRAL

    return _normalize_direction(h4)


# ============================================================
# NIVEAUX CLÉS
# ============================================================

def _nearest_resistance(
    current_price: float,
    candles_h1: list[Candle],
    candles_m15: list[Candle],
) -> Optional[float]:

    levels = (
        _swing_highs(candles_h1)
        + _swing_highs(candles_m15)
    )

    above = [
        level
        for level in levels
        if level > current_price
    ]

    if not above:
        return None

    return min(above)


def _nearest_support(
    current_price: float,
    candles_h1: list[Candle],
    candles_m15: list[Candle],
) -> Optional[float]:

    levels = (
        _swing_lows(candles_h1)
        + _swing_lows(candles_m15)
    )

    below = [
        level
        for level in levels
        if level < current_price
    ]

    if not below:
        return None

    return max(below)


def _find_key_level(
    direction: Direction,
    current_price: float,
    candles_h1: list[Candle],
    candles_m15: list[Candle],
) -> Optional[float]:

    direction = _normalize_direction(direction)

    if direction == Direction.BUY:
        return _nearest_resistance(
            current_price,
            candles_h1,
            candles_m15,
        )

    if direction == Direction.SELL:
        return _nearest_support(
            current_price,
            candles_h1,
            candles_m15,
        )

    return None


# ============================================================
# BREAKOUT
# ============================================================

def _detect_breakout(
    candles: list[Candle],
    level: float,
    direction: Direction,
) -> tuple[bool, int]:

    direction = _normalize_direction(direction)

    if level <= 0:
        return False, -1

    # On cherche une cassure récente.
    start = max(1, len(candles) - 25)

    for index in range(start, len(candles)):

        candle = candles[index]

        if candle.range <= 0:
            continue

        body_ratio = candle.body_ratio

        if body_ratio < BREAKOUT_BODY_RATIO:
            continue

        previous = candles[index - 1]

        if direction == Direction.BUY:

            if (
                previous.close <= level
                and candle.close > level
            ):
                logger.debug(
                    "BREAKOUT BUY détecté à %s",
                    candle.timestamp,
                )
                return True, index

        elif direction == Direction.SELL:

            if (
                previous.close >= level
                and candle.close < level
            ):
                logger.debug(
                    "BREAKOUT SELL détecté à %s",
                    candle.timestamp,
                )
                return True, index

    return False, -1


# ============================================================
# RETEST
# ============================================================

def _detect_retest(
    candles: list[Candle],
    level: float,
    direction: Direction,
    breakout_index: int,
) -> tuple[bool, int]:

    direction = _normalize_direction(direction)

    if breakout_index < 0:
        return False, -1

    # Les bougies après la cassure
    for index in range(
        breakout_index + 1,
        len(candles),
    ):

        candle = candles[index]

        touched = (
            candle.low <= level <= candle.high
        )

        if not touched:
            continue

        if direction == Direction.BUY:

            # Retest d'une résistance devenue support
            if candle.close >= level:
                return True, index

        elif direction == Direction.SELL:

            # Retest d'un support devenu résistance
            if candle.close <= level:
                return True, index

    return False, -1


# ============================================================
# REJECTION
# ============================================================

def _detect_rejection(
    candle: Optional[Candle],
    level: float,
    direction: Direction,
) -> bool:

    if candle is None:
        return False

    if candle.range <= 0:
        return False

    direction = _normalize_direction(direction)

    if direction == Direction.BUY:

        # Mèche basse = rejet des prix sous le niveau
        lower_wick = candle.lower_wick

        return (
            candle.close >= level
            and lower_wick >= candle.body * 0.8
        )

    if direction == Direction.SELL:

        # Mèche haute = rejet des prix au-dessus du niveau
        upper_wick = candle.upper_wick

        return (
            candle.close <= level
            and upper_wick >= candle.body * 0.8
        )

    return False


# ============================================================
# BOUGIE DE CONFIRMATION
# ============================================================

def _confirmation_candle(
    candle: Optional[Candle],
    direction: Direction,
) -> bool:

    if candle is None:
        return False

    if candle.range <= 0:
        return False

    if candle.body_ratio < CONFIRMATION_BODY_RATIO:
        return False

    direction = _normalize_direction(direction)

    if direction == Direction.BUY:
        return candle.bullish

    if direction == Direction.SELL:
        return candle.bearish

    return False


# ============================================================
# SETUP PRICE ACTION
# ============================================================

def build_price_action_setup(
    direction: Direction,
    current_price: float,
    candles_h1: list[Candle],
    candles_m15: list[Candle],
    timeframe_for_zone: str = "M15",
) -> Optional[dict[str, Any]]:

    direction = _normalize_direction(direction)

    if direction == Direction.NEUTRAL:
        return None

    level = _find_key_level(
        direction,
        current_price,
        candles_h1,
        candles_m15,
    )

    if level is None:
        logger.info(
            "SETUP %s : aucun niveau clé trouvé",
            direction.value,
        )
        return None

    atr = _atr(candles_m15)

    if atr <= 0:
        logger.warning(
            "SETUP %s : ATR M15 invalide",
            direction.value,
        )
        return None

    # --------------------------------------------------------
    # Cassure
    # --------------------------------------------------------

    breakout_confirmed, breakout_index = _detect_breakout(
        candles_m15,
        level,
        direction,
    )

    if not breakout_confirmed:

        logger.info(
            "SETUP %s : WAIT — cassure absente | niveau=%.5f",
            direction.value,
            level,
        )

        return {
            "ready": False,
            "reason": "BREAKOUT_NOT_CONFIRMED",
            "level": level,
            "atr": atr,
            "breakout_confirmed": False,
            "breakout_index": -1,
            "retest_confirmed": False,
            "retest_index": -1,
            "rejection_confirmed": False,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # --------------------------------------------------------
    # Retest
    # --------------------------------------------------------

    retest_confirmed, retest_index = _detect_retest(
        candles_m15,
        level,
        direction,
        breakout_index,
    )

    if not retest_confirmed:

        logger.info(
            "SETUP %s : WAIT — retest absent | niveau=%.5f",
            direction.value,
            level,
        )

        return {
            "ready": False,
            "reason": "RETEST_NOT_CONFIRMED",
            "level": level,
            "atr": atr,
            "breakout_confirmed": True,
            "breakout_index": breakout_index,
            "retest_confirmed": False,
            "retest_index": -1,
            "rejection_confirmed": False,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # --------------------------------------------------------
    # Rejet
    # --------------------------------------------------------

    retest_candle = candles_m15[retest_index]

    rejection_confirmed = _detect_rejection(
        retest_candle,
        level,
        direction,
    )

    if not rejection_confirmed:

        logger.info(
            "SETUP %s : WAIT — rejet absent | niveau=%.5f",
            direction.value,
            level,
        )

        return {
            "ready": False,
            "reason": "REJECTION_NOT_CONFIRMED",
            "level": level,
            "atr": atr,
            "breakout_confirmed": True,
            "breakout_index": breakout_index,
            "retest_confirmed": True,
            "retest_index": retest_index,
            "rejection_confirmed": False,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    confirmation_index = min(
        retest_index + 1,
        len(candles_m15) - 1,
    )

    confirmation = candles_m15[
        confirmation_index
    ]

    candle_confirmation = _confirmation_candle(
        confirmation,
        direction,
    )

    if not candle_confirmation:

        logger.info(
            "SETUP %s : WAIT — bougie confirmation absente",
            direction.value,
        )

        return {
            "ready": False,
            "reason": "CANDLE_NOT_CONFIRMED",
            "level": level,
            "atr": atr,
            "breakout_confirmed": True,
            "breakout_index": breakout_index,
            "retest_confirmed": True,
            "retest_index": retest_index,
            "rejection_confirmed": True,
            "candle_confirmation": False,
            "entry_valid": False,
        }

    # --------------------------------------------------------
    # Géométrie d'entrée
    # --------------------------------------------------------

    distance = abs(
        current_price - level
    )

    entry_valid = (
        distance <= atr * ENTRY_MAX_ATR
    )

    if not entry_valid:

        logger.info(
            "SETUP %s : WAIT — prix trop éloigné du niveau "
            "| distance=%.5f | ATR=%.5f",
            direction.value,
            distance,
            atr,
        )

        return {
            "ready": False,
            "reason": "ENTRY_TOO_FAR_FROM_ZONE",
            "level": level,
            "atr": atr,
            "breakout_confirmed": True,
            "breakout_index": breakout_index,
            "retest_confirmed": True,
            "retest_index": retest_index,
            "rejection_confirmed": True,
            "candle_confirmation": True,
            "entry_valid": False,
            "entry_distance": distance,
        }

    logger.info(
        "SETUP %s : READY | niveau=%.5f | prix=%.5f",
        direction.value,
        level,
        current_price,
    )

    return {
        "ready": True,
        "reason": "SETUP_READY",
        "level": level,
        "atr": atr,
        "breakout_confirmed": True,
        "breakout_index": breakout_index,
        "retest_confirmed": True,
        "retest_index": retest_index,
        "rejection_confirmed": True,
        "candle_confirmation": True,
        "entry_valid": True,
        "entry_distance": distance,
    }


# ============================================================
# ZONE
# ============================================================

def build_zone_from_setup(
    setup: dict[str, Any],
    direction: Direction,
    candles_h1: list[Candle],
    candles_m15: list[Candle],
) -> Optional[Zone]:

    if not setup:
        return None

    level = _safe_float(
        setup.get("level"),
    )

    atr = _safe_float(
        setup.get("atr"),
    )

    if level <= 0:
        return None

    if atr <= 0:
        return None

    zone_width = max(
        atr * 0.20,
        level * 0.0001,
    )

    if direction == Direction.BUY:

        low = level - zone_width
        high = level + zone_width

        level_type = "RESISTANCE"

    elif direction == Direction.SELL:

        low = level - zone_width
        high = level + zone_width

        level_type = "SUPPORT"

    else:
        return None

    return Zone(
        direction=direction,
        timeframe="M15",
        low=low,
        high=high,
        h1_strength=1.0,
        m15_strength=1.0,
        kind="PRICE_ACTION_RETEST",
        structure_confirmed=True,
        liquidity_nearby=True,
        order_block=False,
        fvg=False,
        created_at=_now_utc(),
        level_type=level_type,
        key_level=level,
        breakout_confirmed=bool(
            setup.get("breakout_confirmed")
        ),
        breakout_direction=direction,
        retest_confirmed=bool(
            setup.get("retest_confirmed")
        ),
        rejection_confirmed=bool(
            setup.get("rejection_confirmed")
        ),
        candle_confirmation=bool(
            setup.get("candle_confirmation")
        ),
        entry_valid=bool(
            setup.get("entry_valid")
        ),
        entry_distance=_safe_float(
            setup.get("entry_distance")
        ),
    )


# ============================================================
# M5 — MICRO STRUCTURE
# ============================================================

def _m5_micro_bos(
    candles: list[Candle],
    direction: Direction,
) -> bool:

    if len(candles) < 12:
        return False

    recent = candles[-8:]

    highs = _swing_highs(recent)
    lows = _swing_lows(recent)

    direction = _normalize_direction(direction)

    if direction == Direction.BUY:

        if len(highs) >= 2:
            return highs[-1] > highs[-2]

        return recent[-1].close > recent[-3].high

    if direction == Direction.SELL:

        if len(lows) >= 2:
            return lows[-1] < lows[-2]

        return recent[-1].close < recent[-3].low

    return False


def _m5_liquidity_sweep(
    candles: list[Candle],
    direction: Direction,
) -> bool:

    if len(candles) < 8:
        return False

    previous = candles[-2]
    current = candles[-1]

    direction = _normalize_direction(direction)

    recent_high = max(
        candle.high
        for candle in candles[-8:-2]
    )

    recent_low = min(
        candle.low
        for candle in candles[-8:-2]
    )

    if direction == Direction.BUY:

        # Prise de liquidité sous un creux
        return (
            current.low < recent_low
            and current.close > recent_low
        )

    if direction == Direction.SELL:

        # Prise de liquidité au-dessus d'un sommet
        return (
            current.high > recent_high
            and current.close < recent_high
        )

    return False


def _m5_retest(
    candles: list[Candle],
    level: float,
    direction: Direction,
) -> bool:

    if not candles or level <= 0:
        return False

    atr = _atr(candles)

    if atr <= 0:
        return False

    tolerance = atr * 0.25

    recent = candles[-5:]

    for candle in recent:

        if abs(candle.low - level) <= tolerance:
            if direction == Direction.BUY:
                return candle.close >= level

        if abs(candle.high - level) <= tolerance:
            if direction == Direction.SELL:
                return candle.close <= level

    return False


def _m5_rejection(
    candles: list[Candle],
    level: float,
    direction: Direction,
) -> bool:

    if not candles:
        return False

    candle = candles[-1]

    return _detect_rejection(
        candle,
        level,
        direction,
    )


# ============================================================
# CONFIRMATION M5
# ============================================================

def build_m5_confirmation(
    direction: Direction,
    candles_m5: list[Candle],
    level: float,
) -> Confirmation:

    direction = _normalize_direction(direction)

    if not candles_m5 or direction == Direction.NEUTRAL:

        return Confirmation(
            direction=direction,
            retest=False,
            rejection=False,
            liquidity_sweep=False,
            micro_bos=False,
            candle_confirmation=False,
        )

    micro_bos = _m5_micro_bos(
        candles_m5,
        direction,
    )

    liquidity_sweep = _m5_liquidity_sweep(
        candles_m5,
        direction,
    )

    retest = _m5_retest(
        candles_m5,
        level,
        direction,
    )

    rejection = _m5_rejection(
        candles_m5,
        level,
        direction,
    )

    candle_confirmation = _confirmation_candle(
        candles_m5[-1],
        direction,
    )

    confirmation = Confirmation(
        direction=direction,
        retest=retest,
        rejection=rejection,
        liquidity_sweep=liquidity_sweep,
        micro_bos=micro_bos,
        candle_confirmation=candle_confirmation,
    )

    logger.info(
        "M5 CONFIRMATION | %s | retest=%s | rejection=%s "
        "| sweep=%s | micro_bos=%s | candle=%s",
        direction.value,
        retest,
        rejection,
        liquidity_sweep,
        micro_bos,
        candle_confirmation,
    )

    return confirmation


# ============================================================
# SL STRUCTUREL
# ============================================================

def _build_stop_loss(
    direction: Direction,
    entry: float,
    candles_m15: list[Candle],
    candles_h1: list[Candle],
) -> float:

    direction = _normalize_direction(direction)

    atr = _atr(candles_m15)

    if atr <= 0:
        atr = abs(entry) * 0.002

    if direction == Direction.BUY:

        lows = (
            _swing_lows(candles_m15)
            + _swing_lows(candles_h1)
        )

        below = [
            level
            for level in lows
            if level < entry
        ]

        if below:
            structural = max(below)

            # marge sous la structure
            return structural - atr * 0.15

        return entry - atr * 1.2

    if direction == Direction.SELL:

        highs = (
            _swing_highs(candles_m15)
            + _swing_highs(candles_h1)
        )

        above = [
            level
            for level in highs
            if level > entry
        ]

        if above:
            structural = min(above)

            # marge au-dessus de la structure
            return structural + atr * 0.15

        return entry + atr * 1.2

    return entry


# ============================================================
# TAKE PROFIT
# ============================================================

def _build_take_profit(
    direction: Direction,
    entry: float,
    stop_loss: float,
) -> float:

    direction = _normalize_direction(direction)

    risk = abs(
        entry - stop_loss
    )

    if risk <= 0:
        return entry

    if direction == Direction.BUY:
        return entry + risk * CONFIG.MINIMUM_RR

    if direction == Direction.SELL:
        return entry - risk * CONFIG.MINIMUM_RR

    return entry


# ============================================================
# GÉOMÉTRIE
# ============================================================

def _validate_geometry(
    direction: Direction,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> bool:

    direction = _normalize_direction(direction)

    if direction == Direction.BUY:

        return (
            stop_loss < entry < take_profit
        )

    if direction == Direction.SELL:

        return (
            stop_loss > entry > take_profit
        )

    return False


# ============================================================
# MARCHÉ
# ============================================================

def _check_market_open(
    symbol: str,
) -> tuple[bool, Optional[str]]:

    if is_market_open is None:
        return True, None

    try:

        result = is_market_open(symbol)

        if isinstance(result, tuple):
            return (
                bool(result[0]),
                result[1] if len(result) > 1 else None,
            )

        return bool(result), None

    except TypeError:

        try:
            result = is_market_open()

            if isinstance(result, tuple):
                return (
                    bool(result[0]),
                    result[1] if len(result) > 1 else None,
                )

            return bool(result), None

        except Exception as exc:
            logger.warning(
                "Impossible de vérifier le marché %s : %s",
                symbol,
                exc,
            )
            return True, None

    except Exception as exc:

        logger.warning(
            "Erreur market_hours %s : %s",
            symbol,
            exc,
        )

        return True, None


# ============================================================
# NEWS
# ============================================================

def _check_economic_calendar(
    symbol: str,
) -> tuple[bool, Optional[str]]:

    if economic_filter is None:
        return False, None

    try:

        result = economic_filter(symbol)

        # Version actuelle :
        # (blocked, reason)

        if isinstance(result, tuple):

            blocked = bool(
                result[0]
            )

            reason = (
                result[1]
                if len(result) > 1
                else None
            )

            return blocked, reason

        return bool(result), None

    except Exception as exc:

        logger.warning(
            "Erreur calendrier économique %s : %s",
            symbol,
            exc,
        )

        # Le calendrier ne doit pas faire tomber
        # tout le moteur.
        return False, None


# ============================================================
# SCORE
# ============================================================

def _calculate_score(
    direction: Direction,
    zone: Optional[Zone],
    confirmation: Optional[Confirmation],
    rr: float,
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> float:

    try:

        from scoring.score_engine import (
            calculate_score as external_calculate_score,
        )

        result = external_calculate_score(
            h4=h4,
            h1=h1,
            m15=m15,
            zone=zone,
            confirmation=confirmation,
            rr=rr,
        )

        return max(
            0.0,
            min(
                100.0,
                _safe_float(result),
            ),
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Fallback compatible avec le moteur actuel
    # --------------------------------------------------------

    score = 0.0

    # H4
    if h4 == direction:
        score += 20

    # H1
    if h1 == direction:
        score += 20

    # M15
    if m15 == direction:
        score += 20

    # Qualité zone
    if zone is not None:

        if zone.structure_confirmed:
            score += 3

        if zone.liquidity_nearby:
            score += 3

        if zone.order_block:
            score += 2

        if zone.fvg:
            score += 2

    # M5
    if confirmation is not None:

        if confirmation.retest:
            score += 5

        if confirmation.candle_confirmation:
            score += 5

        if confirmation.liquidity_sweep:
            score += 2.5

        if confirmation.micro_bos:
            score += 2.5

    # RR
    if rr >= 2.0:
        score += 5

    # Marché
    score += 5

    return round(
        max(
            0.0,
            min(100.0, score),
        ),
        2,
    )


# ============================================================
# VALIDATION DE SIGNAL
# ============================================================

def _final_build_signal(
    symbol: str,
    trend: TrendContext,
    zone: Zone,
    confirmation: Confirmation,
    entry: float,
    stop_loss: float,
    take_profit: float,
    h4: Direction,
    h1: Direction,
    m15: Direction,
) -> Optional[Signal]:

    try:

        signal = build_signal(
            symbol=symbol,
            trend=trend,
            zone=zone,
            confirmation=confirmation,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            spread_ok=True,
            session_ok=True,
            h4_direction=h4,
            h1_direction=h1,
            m15_direction=m15,
        )

        return signal

    except TypeError:

        try:

            engine = SignalEngine()

            return engine.build_signal(
                symbol=symbol,
                trend=trend,
                zone=zone,
                confirmation=confirmation,
                entry=entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                spread_ok=True,
                session_ok=True,
                h4_direction=h4,
                h1_direction=h1,
                m15_direction=m15,
            )

        except Exception as exc:

            logger.error(
                "Erreur SignalEngine : %s",
                exc,
                exc_info=True,
            )

            return None

    except Exception as exc:

        logger.error(
            "Erreur build_signal : %s",
            exc,
            exc_info=True,
        )

        return None


# ============================================================
# RÉCUPÉRATION DATA
# ============================================================

def _get_candles(
    symbol: str,
    timeframe: str,
) -> list[Candle]:

    if market_data is None:

        logger.error(
            "DATA : market_data indisponible"
        )

        return []

    try:

        result = market_data.get_candles(
            symbol,
            timeframe,
        )

        return _extract_candles(result)

    except TypeError:

        # Compatibilité éventuelle avec keyword args
        try:

            result = market_data.get_candles(
                symbol=symbol,
                timeframe=timeframe,
            )

            return _extract_candles(result)

        except Exception as exc:

            logger.error(
                "DATA %s %s erreur : %s",
                symbol,
                timeframe,
                exc,
            )

            return []

    except Exception as exc:

        logger.error(
            "DATA %s %s erreur : %s",
            symbol,
            timeframe,
            exc,
        )

        return []


def _get_latest_price(
    symbol: str,
    candles_m5: list[Candle],
) -> float:

    # Le dernier close M5 reste la source principale
    # si disponible.

    if candles_m5:

        price = candles_m5[-1].close

        if price > 0:
            return price

    if market_data is None:
        return 0.0

    try:

        if hasattr(
            market_data,
            "get_latest_price",
        ):

            price = market_data.get_latest_price(
                symbol
            )

            if isinstance(price, dict):

                for key in (
                    "price",
                    "close",
                    "last",
                    "value",
                ):
                    if key in price:
                        return _safe_float(
                            price[key]
                        )

            return _safe_float(price)

        if hasattr(
            market_data,
            "get_price",
        ):

            price = market_data.get_price(
                symbol
            )

            if isinstance(price, dict):

                for key in (
                    "price",
                    "close",
                    "last",
                    "value",
                ):
                    if key in price:
                        return _safe_float(
                            price[key]
                        )

            return _safe_float(price)

    except Exception as exc:

        logger.error(
            "PRICE %s erreur : %s",
            symbol,
            exc,
        )

    return 0.0


# ============================================================
# ANALYSE PRINCIPALE
# ============================================================

def analyze_market(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    symbol = str(symbol).upper().strip()

    logger.info(
        "========== ANALYSE %s ==========",
        symbol,
    )

    result: dict[str, Any] = {
        "symbol": symbol,
        "market_type": _market_type(symbol),
        "status": "WAIT",
        "reason": None,
        "direction": Direction.NEUTRAL,
        "score": 0.0,
        "rr": 0.0,
        "entry": None,
        "stop_loss": None,
        "take_profit": None,
        "signal": None,
        "diagnostics": {},
    }

    # ========================================================
    # 1. DATA
    # ========================================================

    candles_h4 = _get_candles(
        symbol,
        "H4",
    )

    candles_h1 = _get_candles(
        symbol,
        "H1",
    )

    candles_m15 = _get_candles(
        symbol,
        "M15",
    )

    candles_m5 = _get_candles(
        symbol,
        "M5",
    )

    result["diagnostics"]["H4_count"] = len(
        candles_h4
    )

    result["diagnostics"]["H1_count"] = len(
        candles_h1
    )

    result["diagnostics"]["M15_count"] = len(
        candles_m15
    )

    result["diagnostics"]["M5_count"] = len(
        candles_m5
    )

    h4_ok = _validate_candles(
        symbol,
        "H4",
        candles_h4,
        H4_MIN_CANDLES,
    )

    h1_ok = _validate_candles(
        symbol,
        "H1",
        candles_h1,
        H1_MIN_CANDLES,
    )

    m15_ok = _validate_candles(
        symbol,
        "M15",
        candles_m15,
        M15_MIN_CANDLES,
    )

    m5_ok = _validate_candles(
        symbol,
        "M5",
        candles_m5,
        M5_MIN_CANDLES,
    )

    result["diagnostics"]["H4_data_ok"] = h4_ok
    result["diagnostics"]["H1_data_ok"] = h1_ok
    result["diagnostics"]["M15_data_ok"] = m15_ok
    result["diagnostics"]["M5_data_ok"] = m5_ok

    # IMPORTANT :
    # On ne transforme plus une absence de données
    # en Direction.NEUTRAL silencieuse.

    if not h4_ok or not h1_ok or not m15_ok:

        missing = []

        if not h4_ok:
            missing.append("H4")

        if not h1_ok:
            missing.append("H1")

        if not m15_ok:
            missing.append("M15")

        reason = (
            "DONNEES_INSUFFISANTES_"
            + "_".join(missing)
        )

        logger.error(
            "ANALYSE %s : %s",
            symbol,
            reason,
        )

        result.update(
            {
                "status": "WAIT",
                "reason": reason,
            }
        )

        return result

    # ========================================================
    # 2. PRICE
    # ========================================================

    current_price = _get_latest_price(
        symbol,
        candles_m5,
    )

    if current_price <= 0:

        result.update(
            {
                "status": "WAIT",
                "reason": "PRICE_UNAVAILABLE",
            }
        )

        logger.error(
            "PRICE %s : indisponible",
            symbol,
        )

        return result

    result["price"] = current_price

    logger.info(
        "PRICE %s : %.8f",
        symbol,
        current_price,
    )

    # ========================================================
    # 3. DIRECTIONS
    # ========================================================

    h4_direction = _structure_direction(
        candles_h4
    )

    h1_direction = _structure_direction(
        candles_h1
    )

    m15_direction = _structure_direction(
        candles_m15
    )

    m5_direction = (
        _structure_direction(candles_m5)
        if m5_ok
        else Direction.NEUTRAL
    )

    result["diagnostics"].update(
        {
            "H4_direction": h4_direction,
            "H1_direction": h1_direction,
            "M15_direction": m15_direction,
            "M5_direction": m5_direction,
        }
    )

    logger.info(
        "DIRECTIONS %s | H4=%s | H1=%s | M15=%s | M5=%s",
        symbol,
        h4_direction.value,
        h1_direction.value,
        m15_direction.value,
        m5_direction.value,
    )

    # ========================================================
    # 4. ALIGNEMENT PRINCIPAL
    # ========================================================

    aligned = is_primary_alignment_valid(
        h4_direction,
        h1_direction,
        m15_direction,
    )

    result["diagnostics"]["primary_alignment"] = aligned

    logger.info(
        "ALIGNEMENT %s | H4=%s H1=%s M15=%s | VALID=%s",
        symbol,
        h4_direction.value,
        h1_direction.value,
        m15_direction.value,
        aligned,
    )

    if not aligned:

        result.update(
            {
                "status": "WAIT",
                "reason": "PRIMARY_ALIGNMENT_NOT_CONFIRMED",
                "direction": Direction.NEUTRAL,
            }
        )

        logger.info(
            "WAIT %s : H4/H1/M15 non alignés",
            symbol,
        )

        return result

    primary_direction = get_primary_direction(
        h4_direction,
        h1_direction,
        m15_direction,
    )

    result["direction"] = primary_direction

    logger.info(
        "PRIMARY DIRECTION %s : %s",
        symbol,
        primary_direction.value,
    )

    # ========================================================
    # 5. TREND CONTEXT
    # ========================================================

    trend = TrendContext(
        h4=primary_direction,
        h4_strength=1.0,
    )

    # ========================================================
    # 6. PRICE ACTION SETUP M15
    # ========================================================

    setup = build_price_action_setup(
        direction=primary_direction,
        current_price=current_price,
        candles_h1=candles_h1,
        candles_m15=candles_m15,
        timeframe_for_zone="M15",
    )

    result["diagnostics"]["setup_reason"] = (
        setup.get("reason")
        if setup
        else "NO_SETUP"
    )

    # ========================================================
    # 7. M5 SNIPER
    # ========================================================
    #
    # IMPORTANT :
    #
    # M5 ne peut PAS invalider H4/H1/M15.
    #
    # Si le setup M15 complet est prêt :
    #     → on utilise M5 pour affiner.
    #
    # Si M15 n'est pas encore prêt :
    #     → on reste WAIT.
    #
    # On ne crée donc jamais un signal uniquement parce
    # que M5 donne un mouvement.
    # ========================================================

    if not setup or not setup.get("ready"):

        result.update(
            {
                "status": "WAIT",
                "reason": (
                    setup.get("reason")
                    if setup
                    else "NO_PRICE_ACTION_SETUP"
                ),
            }
        )

        logger.info(
            "WAIT %s : setup Price Action non confirmé | reason=%s",
            symbol,
            result["reason"],
        )

        return result

    level = _safe_float(
        setup.get("level")
    )

    # ========================================================
    # 8. ZONE
    # ========================================================

    zone = build_zone_from_setup(
        setup=setup,
        direction=primary_direction,
        candles_h1=candles_h1,
        candles_m15=candles_m15,
    )

    if zone is None:

        result.update(
            {
                "status": "WAIT",
                "reason": "ZONE_CREATION_FAILED",
            }
        )

        return result

    # ========================================================
    # 9. M5 CONFIRMATION
    # ========================================================

    if m5_ok:

        confirmation = build_m5_confirmation(
            direction=primary_direction,
            candles_m5=candles_m5,
            level=level,
        )

    else:

        # M5 non disponible :
        # il reste secondaire.
        confirmation = Confirmation(
            direction=primary_direction,
            retest=False,
            rejection=False,
            liquidity_sweep=False,
            micro_bos=False,
            candle_confirmation=False,
        )

        logger.warning(
            "M5 %s indisponible : confirmation secondaire "
            "ignorée.",
            symbol,
        )

    # ========================================================
    # 10. ENTRÉE
    # ========================================================

    entry = current_price

    # Entrée précise :
    # le prix doit rester proche du niveau clé.

    atr_m15 = _atr(candles_m15)

    if atr_m15 <= 0:

        result.update(
            {
                "status": "WAIT",
                "reason": "ATR_INVALID",
            }
        )

        return result

    entry_distance = abs(
        entry - level
    )

    if entry_distance > atr_m15 * LEVEL_PROXIMITY_ATR:

        result.update(
            {
                "status": "WAIT",
                "reason": "ENTRY_TOO_FAR_FROM_KEY_LEVEL",
            }
        )

        logger.info(
            "WAIT %s : entrée trop éloignée | "
            "distance=%.8f | max=%.8f",
            symbol,
            entry_distance,
            atr_m15 * LEVEL_PROXIMITY_ATR,
        )

        return result

    # ========================================================
    # 11. SL
    # ========================================================

    stop_loss = _build_stop_loss(
        direction=primary_direction,
        entry=entry,
        candles_m15=candles_m15,
        candles_h1=candles_h1,
    )

    # ========================================================
    # 12. TP
    # ========================================================

    take_profit = _build_take_profit(
        direction=primary_direction,
        entry=entry,
        stop_loss=stop_loss,
    )

    # ========================================================
    # 13. GEOMETRIE
    # ========================================================

    geometry_ok = _validate_geometry(
        primary_direction,
        entry,
        stop_loss,
        take_profit,
    )

    if not geometry_ok:

        result.update(
            {
                "status": "REJECT",
                "reason": "INVALID_ENTRY_SL_TP_GEOMETRY",
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )

        logger.error(
            "REJECT %s : géométrie invalide | "
            "direction=%s entry=%.8f SL=%.8f TP=%.8f",
            symbol,
            primary_direction.value,
            entry,
            stop_loss,
            take_profit,
        )

        return result

    # ========================================================
    # 14. RR
    # ========================================================

    rr = calculate_rr(
        entry,
        stop_loss,
        take_profit,
    )

    result["rr"] = rr

    if rr < CONFIG.MINIMUM_RR:

        result.update(
            {
                "status": "REJECT",
                "reason": "RR_BELOW_MINIMUM",
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )

        logger.info(
            "REJECT %s : RR %.2f < %.2f",
            symbol,
            rr,
            CONFIG.MINIMUM_RR,
        )

        return result

    # ========================================================
    # 15. SCORE
    # ========================================================

    score = _calculate_score(
        direction=primary_direction,
        zone=zone,
        confirmation=confirmation,
        rr=rr,
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
    )

    result["score"] = score

    logger.info(
        "SCORE %s : %.2f/100",
        symbol,
        score,
    )

    if score < CONFIG.SIGNAL_THRESHOLD:

        result.update(
            {
                "status": "REJECT",
                "reason": "SCORE_BELOW_THRESHOLD",
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )

        logger.info(
            "REJECT %s : score %.2f < %.2f",
            symbol,
            score,
            CONFIG.SIGNAL_THRESHOLD,
        )

        return result

    # ========================================================
    # 16. MARCHÉ
    # ========================================================

    market_open, market_reason = _check_market_open(
        symbol
    )

    if not market_open:

        result.update(
            {
                "status": "WAIT",
                "reason": (
                    market_reason
                    or "MARKET_CLOSED"
                ),
            }
        )

        logger.info(
            "WAIT %s : marché fermé",
            symbol,
        )

        return result

    # ========================================================
    # 17. CALENDRIER ÉCONOMIQUE
    # ========================================================

    news_blocked, news_reason = (
        _check_economic_calendar(symbol)
    )

    if news_blocked:

        result.update(
            {
                "status": "WAIT",
                "reason": (
                    news_reason
                    or "HIGH_IMPACT_NEWS"
                ),
            }
        )

        logger.info(
            "WAIT %s : annonce économique bloquante | %s",
            symbol,
            result["reason"],
        )

        return result

    # ========================================================
    # 18. SIGNAL FINAL
    # ========================================================

    signal = _final_build_signal(
        symbol=symbol,
        trend=trend,
        zone=zone,
        confirmation=confirmation,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        h4=h4_direction,
        h1=h1_direction,
        m15=m15_direction,
    )

    if signal is None:

        result.update(
            {
                "status": "REJECT",
                "reason": "SIGNAL_ENGINE_REJECTED",
                "entry": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )

        logger.info(
            "REJECT %s : SignalEngine",
            symbol,
        )

        return result

    # ========================================================
    # 19. SIGNAL VALIDÉ
    # ========================================================

    result.update(
        {
            "status": "SIGNAL",
            "reason": "VALIDATED",
            "direction": primary_direction,
            "score": score,
            "rr": rr,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "signal": signal,
            "zone": zone,
            "confirmation": confirmation,
        }
    )

    logger.info(
        "========== SIGNAL VALIDÉ =========="
    )

    logger.info(
        "%s | %s | score=%.2f | RR=%.2f | "
        "entry=%.8f | SL=%.8f | TP=%.8f",
        symbol,
        primary_direction.value,
        score,
        rr,
        entry,
        stop_loss,
        take_profit,
    )

    return result


# ============================================================
# ALIASES COMPATIBILITÉ
# ============================================================

def analyser_marche(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    return analyze_market(symbol)


def analyser_marche_complet(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    return analyze_market(symbol)


def analyse_marche(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    return analyze_market(symbol)


def analyze(
    symbol: str = "XAU/USD",
) -> dict[str, Any]:

    return analyze_market(symbol)


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s - "
            "%(name)s - "
            "%(levelname)s - "
            "%(message)s"
        ),
    )

    result = analyze_market(
        "XAU/USD"
    )

    print()
    print("=" * 60)
    print("NOVA TRADE AI — TEST PIPELINE")
    print("=" * 60)
    print(
        "Symbol     :",
        result.get("symbol"),
    )
    print(
        "Direction  :",
        result.get("direction"),
    )
    print(
        "Status     :",
        result.get("status"),
    )
    print(
        "Reason     :",
        result.get("reason"),
    )
    print(
        "Score      :",
        result.get("score"),
    )
    print(
        "RR         :",
        result.get("rr"),
    )
    print(
        "Entry      :",
        result.get("entry"),
    )
    print(
        "SL         :",
        result.get("stop_loss"),
    )
    print(
        "TP         :",
        result.get("take_profit"),
    )
    print()
    print("DIAGNOSTICS")
    print("-" * 60)

    for key, value in result.get(
        "diagnostics",
        {},
    ).items():

        print(
            f"{key:<25} : {value}"
        )

    print("=" * 60)